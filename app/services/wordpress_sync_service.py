"""
WordPress integration for the **fr-mirror** site: JWT auth, read-only REST queries, and pushing local articles to WordPress.

This module talks to two kinds of endpoints:

1. **Custom plugin routes** (paths like ``/wp-json/fr-mirror/v2/...``) — create/update posts and list
   YouTube IDs already published. Paths default to constants in this file but can be overridden via env
   (see :class:`WordPressSyncService`).
2. **Core WordPress REST** ``wp/v2/article`` — paginated article lists with ``context=edit`` for audits,
   meeting-date sorting (theme hook), and featured-image repair scans.

**Authentication**

Uses ``WORDPRESS_JWT_TOKEN`` in the ``Authorization: Bearer`` header when set. Obtained/refreshed via
:meth:`WordPressSyncService.refresh_jwt_token` (``WORDPRESS_JWT_USER`` / ``WORDPRESS_JWT_PASSWORD`` against
``/wp-json/jwt-auth/v1/token``). :meth:`WordPressSyncService._request_with_jwt_retry` retries once after a
``jwt_auth_invalid_token`` 401/403.

**Environment (common)**

- ``WORDPRESS_BASE_URL`` — site origin, no trailing slash required (normalized in code).
- ``WORDPRESS_JWT_TOKEN`` — optional until first protected call; refreshed in-process on success.
- ``WORDPRESS_JWT_USER``, ``WORDPRESS_JWT_PASSWORD`` — for :meth:`~WordPressSyncService.refresh_jwt_token`.
- ``WORDPRESS_API_PATH_CREATE_ARTICLE``, ``WORDPRESS_API_PATH_UPDATE_ARTICLE``,
  ``WORDPRESS_API_PATH_ARTICLE_YOUTUBE_IDS`` — optional path overrides.

**Return conventions**

Public operations that perform HTTP or validation typically return a ``dict`` with ``success`` (``bool``),
``error`` or ``message``, and HTTP-oriented keys like ``status_code`` / ``http_status`` where applicable,
so routers can JSON-serialize without catching exceptions. Read helpers that fail log and return empty
collections (``set()`` / ``[]``) instead of raising.
"""

import base64
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

import requests
from fastapi import status

from app.data.create_database import Database

logger = logging.getLogger(__name__)

# fr-mirror REST API paths (under WORDPRESS_BASE_URL). Override with WORDPRESS_API_PATH_* env vars.
DEFAULT_API_PATH_CREATE = "/wp-json/fr-mirror/v2/create-article"
DEFAULT_API_PATH_UPDATE = "/wp-json/fr-mirror/v2/update-article"
DEFAULT_API_PATH_YOUTUBE_IDS = "/wp-json/fr-mirror/v2/article-youtube-ids"


class WordPressSyncService:
    """
    Bridge between local :class:`~app.data.create_database.Database` rows and the WordPress site.

    **Auth / diagnostics**

    - :meth:`refresh_jwt_token`, :meth:`test_jwt_get`
    - Internal: :meth:`_headers`, :meth:`_request_with_jwt_retry`

    **Read-only WordPress**

    - :meth:`get_article_youtube_ids` — fr-mirror plugin set of IDs already published
    - :meth:`get_article_audit_data_from_wordpress` — full ``wp/v2/article`` listing for diff/audit
    - :meth:`get_articles_sorted_by_meeting_date` — server-side sort via theme REST filter

    **Writes / sync**

    - :meth:`sync_one_article` — DB article → create-article (draft), requires content, bullets, art
    - :meth:`update_article_title_and_content` — partial update endpoint
    - :meth:`repair_article_featured_image` — featured image only by ``youtube_id``
    - :meth:`repair_missing_featured_images` — scan WP posts and repair broken/missing featured_media

    The optional ``database`` may be ``None``; methods that need SQLite return structured errors instead
    of raising.
    """

    def __init__(
        self,
        database: Optional[Database],
        base_url: Optional[str] = None,
        api_path_create: Optional[str] = None,
        api_path_update: Optional[str] = None,
        api_path_youtube_ids: Optional[str] = None,
    ) -> None:
        """
        Args:
            database: Local SQLite access; required for sync/repair methods that read ``articles`` / ``art``.
            base_url: WordPress origin. Defaults to ``WORDPRESS_BASE_URL``; stripped and normalized (no trailing ``/``).
            api_path_create: Defaults to env ``WORDPRESS_API_PATH_CREATE_ARTICLE`` or
                :data:`DEFAULT_API_PATH_CREATE`.
            api_path_update: Env ``WORDPRESS_API_PATH_UPDATE_ARTICLE`` or :data:`DEFAULT_API_PATH_UPDATE`.
            api_path_youtube_ids: Env ``WORDPRESS_API_PATH_ARTICLE_YOUTUBE_IDS`` or
                :data:`DEFAULT_API_PATH_YOUTUBE_IDS`.
        """
        self._database = database
        self._base_url = (base_url if base_url is not None else os.environ.get("WORDPRESS_BASE_URL", "")).strip().rstrip("/")
        self._api_path_create = api_path_create or os.environ.get("WORDPRESS_API_PATH_CREATE_ARTICLE") or DEFAULT_API_PATH_CREATE
        self._api_path_update = api_path_update or os.environ.get("WORDPRESS_API_PATH_UPDATE_ARTICLE") or DEFAULT_API_PATH_UPDATE
        self._api_path_youtube_ids = api_path_youtube_ids or os.environ.get("WORDPRESS_API_PATH_ARTICLE_YOUTUBE_IDS") or DEFAULT_API_PATH_YOUTUBE_IDS

    def _headers(self) -> Dict[str, str]:
        """JSON request headers; adds ``Authorization: Bearer`` when ``WORDPRESS_JWT_TOKEN`` is set."""
        h = {"Content-Type": "application/json"}
        jwt = (os.environ.get("WORDPRESS_JWT_TOKEN") or "").strip()
        if jwt:
            h["Authorization"] = f"Bearer {jwt}"
        return h

    def _is_jwt_invalid_token_response(self, response: requests.Response) -> bool:
        """Return True if response indicates jwt_auth_invalid_token (WordPress uses 401 or 403)."""
        if response.status_code not in (401, 403):
            return False
        text = (response.text or "").strip()
        if "jwt_auth_invalid_token" in text:
            return True
        try:
            data = response.json()
            return (data.get("code") or "") == "jwt_auth_invalid_token"
        except ValueError:
            return False

    def _request_with_jwt_retry(self, request_fn: Callable[[], requests.Response]) -> requests.Response:
        """
        Execute ``request_fn`` (typically a closure over ``requests.get/post``).

        If the response looks like ``jwt_auth_invalid_token``, calls :meth:`refresh_jwt_token`
        and retries **once**; otherwise returns the first response.
        """
        response = request_fn()
        if not self._is_jwt_invalid_token_response(response):
            return response
        logger.info("WordPress returned jwt_auth_invalid_token; refreshing JWT and retrying once.")
        refresh = self.refresh_jwt_token()
        if not refresh.get("success"):
            return response
        return request_fn()

    def refresh_jwt_token(self) -> Dict[str, Any]:
        """
        Obtain a JWT from WordPress ``jwt-auth`` and store it in ``os.environ``.

        POSTs to ``{WORDPRESS_BASE_URL}/wp-json/jwt-auth/v1/token`` with
        ``WORDPRESS_JWT_USER`` and ``WORDPRESS_JWT_PASSWORD``. On success sets
        ``WORDPRESS_JWT_TOKEN`` for subsequent :meth:`_headers` calls.

        Returns:
            Dict with ``success`` (bool), ``status_code`` (int), and ``error`` (``str`` or ``None``).
            On request failure ``error`` holds body or exception text.
        """
        base_url = (self._base_url or "").rstrip("/")
        if not base_url:
            return {
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": "WORDPRESS_BASE_URL is not set or is blank.",
            }
        username = (os.environ.get("WORDPRESS_JWT_USER") or "").strip()
        password = os.environ.get("WORDPRESS_JWT_PASSWORD") or ""
        if not username or not password:
            return {
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": "WORDPRESS_JWT_USER or WORDPRESS_JWT_PASSWORD is not set.",
            }
        url = f"{base_url}/wp-json/jwt-auth/v1/token"
        try:
            response = requests.post(
                url,
                json={"username": username, "password": password},
                timeout=15,
            )
            if not (200 <= response.status_code < 300):
                body = response.text or ""
                logger.warning(
                    "WordPress JWT token request failed: status=%s body=%s",
                    response.status_code,
                    body,
                )
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": body or f"HTTP {response.status_code}",
                }
            try:
                data = response.json()
            except ValueError:
                logger.warning("WordPress JWT token response was not valid JSON: %s", (response.text or "")[:500])
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": "Token endpoint did not return JSON.",
                }
            token = (data.get("token") or "").strip()
            if not token:
                logger.warning("WordPress JWT token response missing 'token' field: %s", data)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": "Token endpoint response missing 'token' field.",
                }
            os.environ["WORDPRESS_JWT_TOKEN"] = token
            logger.info("Refreshed WordPress JWT token successfully.")
            return {
                "success": True,
                "status_code": response.status_code,
                "error": None,
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            status_code = resp.status_code if resp is not None else status.HTTP_502_BAD_GATEWAY
            body = (resp.text if resp is not None and resp.text else None) or str(e)
            logger.error(
                "WordPress JWT token POST failed: %s | status=%s body=%s",
                repr(e),
                status_code,
                body,
            )
            return {
                "success": False,
                "status_code": status_code,
                "error": body,
            }

    def get_article_youtube_ids(self, base_url: Optional[str] = None) -> Set[str]:
        """
        GET fr-mirror ``article-youtube-ids`` and return the published YouTube ID set.

        Appends ``nocache`` timestamp to avoid stale CDN caches. Uses :meth:`_request_with_jwt_retry`.

        Args:
            base_url: Optional origin override; defaults to configured ``_base_url``.

        Returns:
            Set of non-empty ``youtube_id`` strings. On any failure logs a warning and returns ``set()``.
        """
        url = (base_url or self._base_url) + self._api_path_youtube_ids
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}nocache={int(time.time())}"
        try:
            r = self._request_with_jwt_retry(
                lambda: requests.get(url, headers=self._headers(), timeout=15)
            )
            if r.status_code in (401, 403):
                logger.warning(
                    "WordPress returned %s for article-youtube-ids: %s", r.status_code, url
                )
            r.raise_for_status()
            data = r.json()
            raw = data.get("youtube_ids") or []
            return set((yid or "").strip() for yid in raw if (yid or "").strip())
        except Exception as e:
            resp = getattr(e, "response", None)
            logger.warning(
                "get_article_youtube_ids failed: %s | response: status=%s body=%s",
                repr(e),
                resp.status_code if resp is not None else None,
                (resp.text if resp is not None and resp.text else None),
            )
            return set()

    def test_jwt_get(self) -> Dict[str, Any]:
        """
        Read-only probe: GET the article-youtube-ids endpoint with current JWT.

        Does not create or mutate WordPress content. Useful for health checks.

        Returns:
            Dict with ``success`` (2xx), ``status_code``, optional ``response_body`` preview
            (count + first five IDs), ``error`` / ``raw_response`` on failure.
        """
        url = self._base_url + self._api_path_youtube_ids
        url = f"{url}?nocache={int(time.time())}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            response_body: Optional[Dict[str, Any]] = None
            try:
                data = r.json()
                raw = data.get("youtube_ids") or []
                response_body = {"youtube_ids_count": len(raw), "youtube_ids": list(raw)[:5]}
            except Exception:
                response_body = None
            return {
                "success": 200 <= r.status_code < 300,
                "status_code": r.status_code,
                "response_body": response_body,
                "error": None if r.ok else (r.text or f"HTTP {r.status_code}"),
                "raw_response": None if r.ok else (r.text or None),
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            logger.warning(
                "WordPress JWT test GET failed: %s | response: status=%s body=%s",
                repr(e),
                resp.status_code if resp is not None else None,
                (resp.text if resp is not None and resp.text else None),
            )
            return {
                "success": False,
                "status_code": getattr(resp, "status_code", None) or -1,
                "response_body": None,
                "error": str(e),
                "raw_response": resp.text if resp is not None and resp.text else None,
            }

    def get_article_audit_data_from_wordpress(self) -> List[Dict[str, Any]]:
        """
        Page through ``wp/v2/article`` (``context=edit``, 100 per page) for audit / diff tooling.

        Normalizes each post to ``youtube_id``, ``post_id``, ``title``, ``content`` using meta
        ``_article_youtube_id`` and ``_article_content`` where present.

        Returns:
            List of dict rows, or ``[]`` if any request fails (warning logged).
        """
        base = self._base_url.rstrip("/")
        all_items: List[Dict[str, Any]] = []
        page = 1
        try:
            while True:
                url = f"{base}/wp-json/wp/v2/article?per_page=100&context=edit&page={page}"
                r = requests.get(url, headers=self._headers(), timeout=15)
                if r.status_code == 401:
                    logger.warning("WordPress returned 401 for wp/v2/article (audit): %s", url)
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list):
                    break
                for item in data:
                    meta = item.get("meta") or {}
                    yid = (meta.get("_article_youtube_id") or "")
                    yid = (yid if isinstance(yid, str) else str(yid)).strip()
                    title_obj = item.get("title") or {}
                    title = title_obj.get("raw") or title_obj.get("rendered") or ""
                    title = title if isinstance(title, str) else str(title)
                    content = meta.get("_article_content") or (item.get("content") or {}).get("raw") or ""
                    content = content if isinstance(content, str) else str(content)
                    all_items.append({
                        "youtube_id": yid,
                        "post_id": item.get("id"),
                        "title": title,
                        "content": content,
                    })
                total_header = r.headers.get("X-WP-Total")
                total = int(total_header) if total_header is not None and str(total_header).isdigit() else len(data)
                if len(data) < 100 or len(all_items) >= total:
                    break
                page += 1
            return all_items
        except Exception as e:
            resp = getattr(e, "response", None)
            logger.warning(
                "get_article_audit_data_from_wordpress failed: %s | response: status=%s body=%s",
                repr(e),
                resp.status_code if resp is not None else None,
                (resp.text if resp is not None and resp.text else None),
            )
            return []

    def get_articles_sorted_by_meeting_date(
        self,
        order: str = "desc",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        **Read-only.** List ``wp/v2/article`` posts sorted server-side by ``_article_meeting_date``.

        Includes full body and ``_article_bullet_points`` meta so callers do not need SQLite.

        Uses the theme's REST sort hook: passing ``__frmCustomFieldFilter=_article_meeting_date``
        triggers ``rest_article_query`` (in functions.php) to set
        ``meta_key=_article_meeting_date, orderby=meta_value``. Articles missing
        ``_article_meeting_date`` are still returned by WP and sort to the end
        on DESC / start on ASC (the theme does not add an EXISTS clause on the REST path).

        Args:
            order: "asc" (oldest first) or "desc" (newest first). Anything else falls back to "desc".
            limit: Max number of items to return. None = all.

        Returns:
            List of dicts:
            ``{post_id, youtube_id, title, meeting_date, content, bullet_points}``,
            in meeting-date order. ``content`` prefers ``_article_content`` meta and
            falls back to the post's raw body; ``bullet_points`` comes from
            ``_article_bullet_points`` meta. Returns ``[]`` on error.
        """
        base = (self._base_url or "").rstrip("/")
        order_norm = "asc" if (order or "").lower() == "asc" else "desc"
        per_page = 100
        out: List[Dict[str, Any]] = []
        page = 1
        try:
            while True:
                if limit is not None and len(out) >= limit:
                    break
                url = (
                    f"{base}/wp-json/wp/v2/article"
                    f"?per_page={per_page}"
                    f"&context=edit"
                    f"&page={page}"
                    f"&__frmCustomFieldFilter=_article_meeting_date"
                    f"&order={order_norm}"
                )
                r = self._request_with_jwt_retry(
                    lambda: requests.get(url, headers=self._headers(), timeout=15)
                )
                if r.status_code in (401, 403):
                    logger.warning(
                        "WordPress returned %s for wp/v2/article (meeting-date sort): %s",
                        r.status_code,
                        url,
                    )
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list) or not data:
                    break
                for item in data:
                    meta = item.get("meta") or {}
                    yid = meta.get("_article_youtube_id") or ""
                    yid = (yid if isinstance(yid, str) else str(yid)).strip()
                    title_obj = item.get("title") or {}
                    title = title_obj.get("rendered") or title_obj.get("raw") or ""
                    title = title if isinstance(title, str) else str(title)
                    md = meta.get("_article_meeting_date") or ""
                    md = (md if isinstance(md, str) else str(md)).strip()
                    content = (
                        meta.get("_article_content")
                        or (item.get("content") or {}).get("raw")
                        or (item.get("content") or {}).get("rendered")
                        or ""
                    )
                    content = content if isinstance(content, str) else str(content)
                    bullet_points = meta.get("_article_bullet_points") or ""
                    bullet_points = (
                        bullet_points if isinstance(bullet_points, str) else str(bullet_points)
                    )
                    out.append({
                        "post_id": item.get("id"),
                        "youtube_id": yid,
                        "title": title,
                        "meeting_date": md,
                        "content": content,
                        "bullet_points": bullet_points,
                    })
                    if limit is not None and len(out) >= limit:
                        break
                if limit is not None and len(out) >= limit:
                    break
                total_header = r.headers.get("X-WP-Total")
                total = (
                    int(total_header)
                    if total_header is not None and str(total_header).isdigit()
                    else len(data)
                )
                if len(data) < per_page or len(out) >= total:
                    break
                page += 1
            return out
        except Exception as e:
            resp = getattr(e, "response", None)
            logger.warning(
                "get_articles_sorted_by_meeting_date failed: %s | response: status=%s body=%s",
                repr(e),
                resp.status_code if resp is not None else None,
                (resp.text if resp is not None and resp.text else None),
            )
            return []

    def repair_missing_featured_images(
        self,
        iteration_limit: Optional[int] = None,
        repair_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Scan WordPress ``wp/v2/article`` posts and repair featured images using local DB art.

        A post is **broken** if ``featured_media`` is set but media has no ``source_url`` or HEAD
        to the URL is not 2xx. **Missing** if there is no ``featured_media``. Good posts are skipped.

        Repairs call :meth:`repair_article_featured_image` (update-article with base64 image); no AI.

        Args:
            iteration_limit: Max posts to inspect (``None`` = until pagination ends or limits satisfied).
            repair_limit: Max successful repairs to attempt (``None`` = unlimited).

        Returns:
            On success: ``success``, ``iteration_limit``, ``repair_limit``, ``scanned``,
            ``broken_or_missing_count``, ``repaired_count``, ``items`` (per-post detail with
            ``status``, ``reason``, ``repaired``, ``repair_error``, etc.).
            On failure: ``success: False``, ``error``, ``http_status``.
        """
        base = (self._base_url or "").rstrip("/")
        if not base:
            return {
                "success": False,
                "error": "WORDPRESS_BASE_URL is not set or is blank.",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
        max_scan = iteration_limit if iteration_limit is not None and iteration_limit > 0 else None
        max_repair = repair_limit if repair_limit is not None and repair_limit >= 0 else None

        scanned = 0
        repaired = 0
        items: List[Dict[str, Any]] = []
        page = 1
        try:
            while True:
                if max_scan is not None and scanned >= max_scan:
                    break
                url = f"{base}/wp-json/wp/v2/article?per_page=100&context=edit&page={page}"
                r = self._request_with_jwt_retry(
                    lambda: requests.get(url, headers=self._headers(), timeout=15)
                )
                if r.status_code in (401, 403):
                    logger.warning(
                        "WordPress returned %s for wp/v2/article (repair_missing_featured_images): %s",
                        r.status_code,
                        url,
                    )
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list) or not data:
                    break

                for item in data:
                    if max_scan is not None and scanned >= max_scan:
                        break
                    scanned += 1

                    meta = item.get("meta") or {}
                    youtube_id_raw = meta.get("_article_youtube_id") or ""
                    youtube_id = (
                        youtube_id_raw if isinstance(youtube_id_raw, str) else str(youtube_id_raw)
                    ).strip()
                    title_obj = item.get("title") or {}
                    title_val = title_obj.get("raw") or title_obj.get("rendered") or ""
                    title = title_val if isinstance(title_val, str) else str(title_val)
                    post_id = item.get("id")

                    status_str: Optional[str] = None
                    reason: Optional[str] = None

                    featured_media_id = item.get("featured_media") or 0
                    if featured_media_id:
                        # Inspect media object and then HEAD the source_url
                        media_url = f"{base}/wp-json/wp/v2/media/{featured_media_id}?context=edit"
                        try:
                            mr = self._request_with_jwt_retry(
                                lambda: requests.get(media_url, headers=self._headers(), timeout=10)
                            )
                            if mr.status_code in (401, 403):
                                logger.warning(
                                    "WordPress returned %s for media %s",
                                    mr.status_code,
                                    media_url,
                                )
                            mr.raise_for_status()
                            media = mr.json()
                            src = (media.get("source_url") or "").strip()
                            if not src:
                                status_str = "broken"
                                reason = "media has no source_url"
                            else:
                                try:
                                    head_resp = requests.head(
                                        src, timeout=10, allow_redirects=True
                                    )
                                    if not (200 <= head_resp.status_code < 300):
                                        status_str = "broken"
                                        reason = f"HEAD {src} returned {head_resp.status_code}"
                                except requests.exceptions.RequestException as he:
                                    status_str = "broken"
                                    reason = f"HEAD {src} failed: {he}"
                        except requests.exceptions.RequestException as me:
                            # If we cannot inspect media, treat as broken so it can be repaired.
                            status_str = "broken"
                            reason = f"Failed to fetch media {featured_media_id}: {me}"
                    else:
                        # No featured_media set at all.
                        status_str = "missing"
                        reason = "no featured_media set"

                    if not status_str:
                        # Image appears OK; skip.
                        continue

                    item_info: Dict[str, Any] = {
                        "post_id": post_id,
                        "title": title,
                        "youtube_id": youtube_id,
                        "status": status_str,
                        "reason": reason,
                        "repaired": False,
                        "repair_error": None,
                    }

                    # Attempt repair only up to repair_limit (if set) and only when we have a youtube_id.
                    should_repair = (
                        youtube_id
                        and (max_repair is None or repaired < max_repair)
                    )
                    if should_repair:
                        result = self.repair_article_featured_image(youtube_id)
                        if result.get("success"):
                            item_info["repaired"] = True
                            repaired += 1
                        else:
                            item_info["repaired"] = False
                            item_info["repair_error"] = (
                                result.get("error") or result.get("response") or "Unknown error"
                            )
                    elif not youtube_id:
                        item_info["repair_error"] = "No youtube_id set on post meta"

                    items.append(item_info)

                # Stop if we reached the end of pages.
                total_header = r.headers.get("X-WP-Total")
                total = (
                    int(total_header)
                    if total_header is not None and str(total_header).isdigit()
                    else len(data)
                )
                if len(data) < 100 or (max_scan is None and scanned >= total) or (
                    max_scan is not None and scanned >= max_scan
                ):
                    break
                page += 1

            return {
                "success": True,
                "iteration_limit": iteration_limit,
                "repair_limit": repair_limit,
                "scanned": scanned,
                "broken_or_missing_count": len(items),
                "repaired_count": repaired,
                "items": items,
            }
        except Exception as e:
            resp = getattr(e, "response", None)
            logger.warning(
                "repair_missing_featured_images failed: %s | response: status=%s body=%s",
                repr(e),
                resp.status_code if resp is not None else None,
                (resp.text if resp is not None and resp.text else None),
            )
            return {
                "success": False,
                "error": str(e),
                "http_status": status.HTTP_502_BAD_GATEWAY,
            }

    def sync_one_article(self, article_id: int) -> Dict[str, Any]:
        """
        Push one local article to WordPress **create-article** as a draft (if not already on WP).

        Loads the row from ``database``, resolves journalist name and ``meeting_date`` from linked
        transcript, builds a data-URL **featured_image** from the first ``art`` row (PNG/JPEG sniff),
        and skips create if :meth:`get_article_youtube_ids` already contains the article's ``youtube_id``.

        **Required fields:** non-empty ``content``, ``bullet_points``, and binary art; otherwise returns
        ``400``-style payload without calling WordPress.

        Args:
            article_id: Primary key in local ``articles``.

        Returns:
            **Skipped:** ``success``, ``article_id``, ``created: False``, ``skipped: True``,
            ``reason: already_on_wordpress``.
            **Created:** ``success``, ``created: True``, ``wordpress_response`` (JSON body).
            **Errors:** ``success: False``, ``error``, ``http_status``, optional ``raw_response``.
        """
        db = self._database
        if not db:
            return {
                "success": False,
                "error": "Database not available",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }

        article = db.get_article_by_id(article_id)
        if not article:
            return {
                "success": False,
                "error": f"Article with ID {article_id} not found",
                "http_status": status.HTTP_404_NOT_FOUND,
            }

        journalist_name = ""
        if article.get("journalist_id"):
            try:
                db.cursor.execute(
                    "SELECT first_name, last_name FROM journalists WHERE id = ?",
                    (article["journalist_id"],),
                )
                journalist_result = db.cursor.fetchone()
                if journalist_result:
                    first_name = journalist_result[0] or ""
                    last_name = journalist_result[1] or ""
                    if first_name and last_name:
                        journalist_name = f"{first_name} {last_name}"
                    elif first_name:
                        journalist_name = first_name
                    elif last_name:
                        journalist_name = last_name
            except Exception as e:
                logger.warning(f"Failed to fetch journalist data: {str(e)}")

        meeting_date = ""
        transcript_id = article.get("transcript_id")
        if transcript_id:
            try:
                db.cursor.execute(
                    "SELECT meeting_date FROM transcripts WHERE id = ?",
                    (transcript_id,),
                )
                transcript_result = db.cursor.fetchone()
                if transcript_result and transcript_result[0]:
                    date_str = transcript_result[0]
                    try:
                        date_obj = None
                        try:
                            date_obj = datetime.strptime(date_str, "%m-%d-%Y")
                        except ValueError:
                            pass
                        if not date_obj:
                            try:
                                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                            except ValueError:
                                pass
                        if not date_obj:
                            try:
                                s = date_str.replace("Z", "+00:00") if date_str.endswith("Z") else date_str
                                date_obj = datetime.fromisoformat(s)
                            except ValueError:
                                pass
                        if not date_obj:
                            try:
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            except ValueError:
                                pass
                        if date_obj:
                            meeting_date = date_obj.strftime("%Y-%m-%d")
                        else:
                            logger.warning(f"Could not parse meeting_date '{date_str}', using as-is")
                            meeting_date = date_str
                    except Exception as e:
                        logger.warning(f"Failed to format meeting_date: {str(e)}, using original value")
                        meeting_date = transcript_result[0]
            except Exception as e:
                logger.warning(f"Failed to fetch meeting_date from transcript: {str(e)}")

        featured_image = None
        try:
            db.cursor.execute(
                "SELECT id, image_data, model FROM art WHERE article_id = ? LIMIT 1",
                (article_id,),
            )
            art_result = db.cursor.fetchone()
            if art_result and art_result[1]:
                image_data = art_result[1]
                if isinstance(image_data, bytes):
                    image_format = "png"
                    if len(image_data) >= 2 and image_data[:2] == b"\xff\xd8":
                        image_format = "jpeg"
                    elif len(image_data) >= 8 and image_data[:8] == b"\x89PNG\r\n\x1a\n":
                        image_format = "png"
                    base64_data = base64.b64encode(image_data).decode("utf-8")
                    featured_image = f"data:image/{image_format};base64,{base64_data}"
        except Exception as e:
            logger.warning(f"Failed to fetch/process image for article {article_id}: {str(e)}", exc_info=True)

        missing_fields = []
        if not article.get("content"):
            missing_fields.append("content")
        if not article.get("bullet_points"):
            missing_fields.append("bullet_points")
        if not featured_image:
            missing_fields.append("featured_image (art)")
        if missing_fields:
            return {
                "success": False,
                "error": f"Article {article_id} is missing required fields for sync: {', '.join(missing_fields)}. Article must have content, bullet points, and art to sync to WordPress.",
                "http_status": status.HTTP_400_BAD_REQUEST,
            }

        youtube_id = (article.get("youtube_id") or "").strip()
        existing_on_wp = youtube_id in self.get_article_youtube_ids() if youtube_id else False

        if existing_on_wp:
            # Already on WordPress: skip. We don't create or update; content is already there.
            logger.info("Skipping article %s (youtube_id=%s already on WordPress)", article_id, youtube_id)
            return {
                "success": True,
                "article_id": article_id,
                "created": False,
                "skipped": True,
                "reason": "already_on_wordpress",
            }
        # New on WordPress: create post
        payload = {
            "title": article.get("title") or "",
            "article_content": article.get("content") or "",
            "journalist_name": journalist_name or "",
            "committee": article.get("committee") or "",
            "youtube_id": youtube_id or "",
            "bullet_points": article.get("bullet_points") or "",
            "meeting_date": meeting_date or "",
            "view_count": article.get("view_count") or 0,
            "featured_image": featured_image or "",
            "status": "draft",
        }
        wordpress_url = self._base_url + self._api_path_create
        try:
            response = self._request_with_jwt_retry(
                lambda: requests.post(
                    wordpress_url,
                    json=payload,
                    headers=self._headers(),
                    timeout=30,
                )
            )
            if response.status_code in (401, 403):
                logger.warning(
                    "WordPress returned %s for create-article: %s",
                    response.status_code,
                    wordpress_url,
                )
            response.raise_for_status()
            logger.info("Successfully synced article %s to WordPress (create)", article_id)
            try:
                wp_response = response.json()
            except (ValueError, TypeError) as e:
                logger.error(
                    "sync_one_article: WordPress returned non-JSON response for article %s: %s",
                    article_id, e,
                )
                return {
                    "success": False,
                    "error": f"WordPress response was not valid JSON: {e}",
                    "http_status": response.status_code,
                    "raw_response": (response.text or "")[:2000],
                }
            return {
                "success": True,
                "article_id": article_id,
                "created": True,
                "skipped": False,
                "wordpress_response": wp_response,
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            status_code = resp.status_code if resp is not None else status.HTTP_502_BAD_GATEWAY
            body = (resp.text if resp is not None and resp.text else None) or ""
            logger.error(
                "sync_one_article POST to WordPress failed: %s | response: status=%s body=%s",
                repr(e),
                status_code,
                body,
            )
            return {
                "success": False,
                "error": body if body else str(e),
                "http_status": status_code,
                "raw_response": body or None,
            }
        except Exception as e:
            logger.error(
                "sync_one_article unexpected error for article %s: %s",
                article_id, e,
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }

    def update_article_title_and_content(self, article_id: int) -> Dict[str, Any]:
        """
        POST current DB **title** and **content** to the fr-mirror **update-article** endpoint.

        Payload includes local ``article_id`` and ``youtube_id`` for WP to locate the post. Does not
        change slug or delete the post (WordPress plugin contract).

        Returns:
            ``success``, ``article_id``, ``wordpress_response`` on 2xx; otherwise ``success: False``,
            ``error``, ``http_status``, ``raw_response``.
        """
        db = self._database
        if not db:
            return {
                "success": False,
                "error": "Database not available",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
        article = db.get_article_by_id(article_id)
        if not article:
            return {
                "success": False,
                "error": f"Article with ID {article_id} not found",
                "http_status": status.HTTP_404_NOT_FOUND,
            }
        payload = {
            "article_id": article_id,
            "youtube_id": (article.get("youtube_id") or "").strip(),
            "title": article.get("title") or "",
            "content": article.get("content") or "",
        }
        url = self._base_url + self._api_path_update
        try:
            response = self._request_with_jwt_retry(
                lambda: requests.post(
                    url,
                    json=payload,
                    headers=self._headers(),
                    timeout=30,
                )
            )
            if response.status_code in (401, 403):
                logger.warning(
                    "WordPress returned %s for update-article: %s",
                    response.status_code,
                    url,
                )
            response.raise_for_status()
            logger.info("Successfully sent title/content update for article_id=%s to WordPress", article_id)
            return {
                "success": True,
                "article_id": article_id,
                "wordpress_response": response.json() if response.content else None,
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            status_code = resp.status_code if resp is not None else status.HTTP_502_BAD_GATEWAY
            body = (resp.text if resp is not None and resp.text else None) or ""
            logger.error(
                "update_article_title_and_content POST to WordPress failed: %s | response: status=%s body=%s",
                repr(e),
                status_code,
                body,
            )
            return {
                "success": False,
                "error": body if body else str(e),
                "http_status": status_code,
                "raw_response": body or None,
            }

    def repair_article_featured_image(self, youtube_id: str) -> Dict[str, Any]:
        """
        Upload featured image bytes from DB to WordPress via **update-article** for a ``youtube_id``.

        Uses :meth:`~app.data.create_database.Database.get_featured_image_by_youtube_id`; encodes
        as data-URL and POSTs ``{youtube_id, featured_image}``.

        Returns:
            Dict with ``success`` (2xx check), ``status_code``, ``response`` (body text),
            and ``_from`` provenance string. On missing DB image or blank base URL, returns
            ``success: False`` with ``error`` / ``http_status``.
        """
        db = self._database
        if not db:
            return {
                "success": False,
                "error": "Database not available",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
        youtube_id = (youtube_id or "").strip()
        image_result = db.get_featured_image_by_youtube_id(youtube_id)
        if not image_result:
            logger.warning("Repair featured image: no image for youtube_id=%s", youtube_id)
            return {
                "success": False,
                "error": "No image for this youtube_id",
                "http_status": status.HTTP_404_NOT_FOUND,
            }
        image_data, image_format = image_result
        base64_data = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:image/{image_format};base64,{base64_data}"
        payload = {"youtube_id": youtube_id, "featured_image": data_url}
        if not (self._base_url or "").strip():
            logger.warning("Repair featured image: WORDPRESS_BASE_URL is not set or blank")
            return {
                "success": False,
                "error": "WORDPRESS_BASE_URL is not set or is blank.",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
        url = (self._base_url or "").rstrip("/") + (self._api_path_update or "")
        logger.info(
            "Repair featured image request: url=%s youtube_id=%s image_size_bytes=%d",
            url, youtube_id, len(image_data),
        )
        try:
            response = self._request_with_jwt_retry(
                lambda: requests.post(
                    url,
                    json=payload,
                    headers=self._headers(),
                    timeout=30,
                )
            )
            logger.info(
                "Repair featured image response: status_code=%s response_body=%s",
                response.status_code, (response.text or "")[:500],
            )
            return {
                "success": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "response": response.text or None,
                "_from": "wordpress_sync_service.repair_article_featured_image",
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            status_code = resp.status_code if resp is not None else status.HTTP_502_BAD_GATEWAY
            body = (resp.text if resp is not None and resp.text else None) or str(e)
            logger.error("Repair featured image POST failed: %s | %s %s", url, status_code, body)
            return {
                "success": False,
                "status_code": status_code,
                "response": body,
                "_from": "wordpress_sync_service.repair_article_featured_image",
            }
