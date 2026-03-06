"""
WordPress sync service: fetch article YouTube IDs from WordPress and sync articles to WordPress.
"""

import base64
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests
from fastapi import status

from app.data.create_database import Database

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://192.168.1.17:9004"
DEFAULT_API_PATH_CREATE = "/wp-json/fr-mirror/v2/create-article"
DEFAULT_API_PATH_UPDATE = "/wp-json/fr-mirror/v2/update-article"
DEFAULT_API_PATH_YOUTUBE_IDS = "/wp-json/fr-mirror/v2/article-youtube-ids"


class WordPressSyncService:
    """
    Syncs articles from the FastAPI database to the WordPress create-article endpoint.
    """

    def __init__(
        self,
        database: Optional[Database],
        base_url: Optional[str] = None,
        api_path_create: Optional[str] = None,
        api_path_update: Optional[str] = None,
        api_path_youtube_ids: Optional[str] = None,
    ) -> None:
        self._database = database
        self._base_url = (base_url or os.environ.get("WORDPRESS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._api_path_create = api_path_create or os.environ.get("WORDPRESS_API_PATH_CREATE_ARTICLE") or DEFAULT_API_PATH_CREATE
        self._api_path_update = api_path_update or os.environ.get("WORDPRESS_API_PATH_UPDATE_ARTICLE") or DEFAULT_API_PATH_UPDATE
        self._api_path_youtube_ids = api_path_youtube_ids or os.environ.get("WORDPRESS_API_PATH_ARTICLE_YOUTUBE_IDS") or DEFAULT_API_PATH_YOUTUBE_IDS
        self._jwt = (os.environ.get("WORDPRESS_JWT_TOKEN") or "").strip()

    def _headers(self) -> Dict[str, str]:
        """Request headers; includes Bearer token when WORDPRESS_JWT_TOKEN is set."""
        h = {"Content-Type": "application/json"}
        if self._jwt:
            h["Authorization"] = f"Bearer {self._jwt}"
        return h

    def get_article_youtube_ids(self, base_url: Optional[str] = None) -> Set[str]:
        """Fetch the set of youtube_ids that already have an article on WordPress. Returns empty set on error."""
        url = (base_url or self._base_url) + self._api_path_youtube_ids
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}nocache={int(time.time())}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 401:
                logger.warning("WordPress returned 401 Unauthorized for article-youtube-ids: %s", url)
            r.raise_for_status()
            data = r.json()
            raw = data.get("youtube_ids") or []
            return set((yid or "").strip() for yid in raw if (yid or "").strip())
        except Exception as e:
            logger.warning(f"Could not fetch WordPress article youtube_ids: {e}")
            return set()

    def test_jwt_get(self) -> Dict[str, Any]:
        """
        Send a GET request to the article-youtube-ids endpoint to verify JWT.
        Read-only; does not create or modify any content. Returns success, status_code, and optional response summary.
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
            }
        except requests.exceptions.RequestException as e:
            logger.warning("WordPress JWT test GET failed: %s", e)
            return {
                "success": False,
                "status_code": -1,
                "response_body": None,
                "error": str(e),
            }

    def get_article_audit_data_from_wordpress(self) -> List[Dict[str, Any]]:
        """
        Fetch all article posts from the built-in WP REST API (wp/v2/article).
        Returns a normalized list of {youtube_id, post_id, title, content} for audit comparison.
        Uses per_page=100 and context=edit; paginates until all articles are fetched.
        Returns empty list on error.
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
            logger.warning("Could not fetch WordPress article audit data: %s", e)
            return []

    def sync_one_article(self, article_id: int) -> Dict[str, Any]:
        """
        Fetch an article from the database and POST it to the WordPress create-article endpoint.
        Returns a result dict; does not raise.
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
            return {"success": True, "article_id": article_id, "skipped": True, "reason": "already_on_wordpress"}
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
            "status": "publish",
        }
        wordpress_url = self._base_url + self._api_path_create
        try:
            response = requests.post(
                wordpress_url,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            if response.status_code == 401:
                logger.warning("WordPress returned 401 Unauthorized for create-article: %s", wordpress_url)
            response.raise_for_status()
            logger.info(f"Successfully synced article {article_id} to WordPress (create)")
            return {
                "success": True,
                "article_id": article_id,
                "wordpress_response": response.json(),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to POST to WordPress: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to sync to WordPress: {str(e)}",
                "http_status": status.HTTP_502_BAD_GATEWAY,
            }

    def update_article_title_and_content(self, article_id: int) -> Dict[str, Any]:
        """
        Send the current article title and content from our DB to WordPress update-article endpoint.
        WordPress should update only title and content of the existing post; do not delete or change slug.
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
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            if response.status_code == 401:
                logger.warning("WordPress returned 401 Unauthorized for update-article: %s", url)
            response.raise_for_status()
            logger.info("Successfully sent title/content update for article_id=%s to WordPress", article_id)
            return {
                "success": True,
                "article_id": article_id,
                "wordpress_response": response.json() if response.content else None,
            }
        except requests.exceptions.RequestException as e:
            logger.error("Failed to POST update-article to WordPress: %s", e)
            return {
                "success": False,
                "error": f"Failed to update article on WordPress: {str(e)}",
                "http_status": status.HTTP_502_BAD_GATEWAY,
            }

    def repair_article_featured_image(self, youtube_id: str) -> Dict[str, Any]:
        """
        Repair the WordPress post's featured image from the article's art in SQLite (fixes broken image link).
        Resolves article by youtube_id, gets art image_data from DB, builds base64 data URL,
        and POSTs to WordPress update-article with featured_image.
        """
        db = self._database
        if not db:
            return {
                "success": False,
                "error": "Database not available",
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
        youtube_id = (youtube_id or "").strip()
        if not youtube_id:
            return {
                "success": False,
                "error": "youtube_id is required",
                "http_status": status.HTTP_400_BAD_REQUEST,
            }
        article = db.get_article_by_youtube_id(youtube_id)
        if not article:
            return {
                "success": False,
                "error": "Article not found for youtube_id",
                "http_status": status.HTTP_404_NOT_FOUND,
            }
        art = db.get_art_by_article_id(article["id"])
        if not art or not art.get("image_data"):
            return {
                "success": False,
                "error": "No image for this article",
                "http_status": status.HTTP_404_NOT_FOUND,
            }
        image_data = art["image_data"]
        if not isinstance(image_data, bytes):
            return {
                "success": False,
                "error": "No image for this article",
                "http_status": status.HTTP_404_NOT_FOUND,
            }
        image_format = "png"
        if len(image_data) >= 2 and image_data[:2] == b"\xff\xd8":
            image_format = "jpeg"
        elif len(image_data) >= 8 and image_data[:8] == b"\x89PNG\r\n\x1a\n":
            image_format = "png"
        base64_data = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:image/{image_format};base64,{base64_data}"
        payload = {"youtube_id": youtube_id, "featured_image": data_url}
        url = self._base_url + self._api_path_update
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            if response.status_code == 401:
                logger.warning("WordPress returned 401 Unauthorized for update-article (repair featured image): %s", url)
            response.raise_for_status()
            logger.info("Successfully repaired featured image for youtube_id=%s on WordPress", youtube_id)
            return {
                "success": True,
                "youtube_id": youtube_id,
                "wordpress_response": response.json() if response.content else None,
            }
        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            status_code = resp.status_code if resp is not None else status.HTTP_502_BAD_GATEWAY
            err_msg = (resp.text[:500] if resp is not None and resp.text else str(e))
            logger.error("Failed to POST update-article (repair featured image) to WordPress: %s", e)
            return {
                "success": False,
                "error": err_msg,
                "http_status": status_code,
            }
