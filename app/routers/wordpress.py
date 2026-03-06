"""WordPress sync endpoints."""

import difflib
import html
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import AppDependencies


class RepairArticleFeaturedImageBody(BaseModel):
    """Request body for repair-article-featured-image."""

    youtube_id: str = Field(..., min_length=1, description="YouTube ID of the article")

router = APIRouter(tags=["wordpress"])
logger = logging.getLogger(__name__)


@router.get("/wordpress/test-jwt")
def test_jwt(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Verify JWT against the configured WordPress base URL (read-only; GET to article-youtube-ids)."""
    if not deps.wordpress_sync_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    result = deps.wordpress_sync_service.test_jwt_get()
    if not result["success"] and result.get("status_code") == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result.get("error", "JWT rejected"))
    return result


@router.post("/sync-article-to-wordpress/{article_id}")
def sync_article_to_wordpress(
    article_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Fetch an article from the FastAPI database and POST it to the WordPress create-article endpoint."""
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    svc = deps.wordpress_sync_service
    if not svc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    result = svc.sync_one_article(article_id)
    if not result["success"]:
        raise HTTPException(
            status_code=result.get("http_status", status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=result.get("error", "Sync failed"),
        )
    return result


@router.post("/wordpress/repair-article-featured-image")
def repair_article_featured_image(
    body: RepairArticleFeaturedImageBody,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Repair the WordPress post's featured image from the article's art in SQLite (fixes broken image link)."""
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    if not deps.wordpress_sync_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    result = deps.wordpress_sync_service.repair_article_featured_image(body.youtube_id)
    if not result["success"]:
        raise HTTPException(
            status_code=result.get("http_status", status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=result.get("error", "Repair featured image failed"),
        )
    return result


@router.post("/sync-articles-to-wordpress")
def sync_all_articles_to_wordpress(
    limit: Optional[int] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Sync multiple articles to WordPress in bulk."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        svc = deps.wordpress_sync_service
        if not svc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="WordPress sync service not available",
            )
        all_articles = deps.database.get_all_articles()
        if limit is not None and limit > 0:
            articles_to_sync = all_articles[:limit]
        else:
            articles_to_sync = all_articles
        if not articles_to_sync:
            return {
                "success": True,
                "total_articles": 0,
                "synced": 0,
                "failed": 0,
                "errors": [],
                "message": "No articles found to sync",
            }
        logger.info(f"Starting bulk sync to WordPress: {len(articles_to_sync)} articles")
        synced_count = 0
        failed_count = 0
        errors = []
        for article in articles_to_sync:
            article_id = article.get("id")
            if not article_id:
                failed_count += 1
                errors.append({"article_id": None, "error": "Article missing ID field"})
                continue
            result = svc.sync_one_article(article_id)
            if result.get("success"):
                synced_count += 1
            else:
                failed_count += 1
                errors.append({"article_id": article_id, "error": result.get("error", "Unknown error")})
                logger.warning(f"Failed to sync article {article_id}: {result.get('error')}")
        logger.info(f"Bulk sync complete: {synced_count} succeeded, {failed_count} failed")
        return {
            "success": True,
            "total_articles": len(articles_to_sync),
            "synced": synced_count,
            "failed": failed_count,
            "errors": errors,
            "message": f"Synced {synced_count} of {len(articles_to_sync)} articles to WordPress",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk sync to WordPress failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk sync to WordPress failed: {str(e)}",
        )


@router.post("/sync-missing-articles-to-wordpress")
def sync_missing_articles_to_wordpress(
    limit: Optional[int] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Sync to WordPress only articles that do not already exist on the site (by youtube_id)."""
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    svc = deps.wordpress_sync_service
    if not svc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    existing_youtube_ids = svc.get_article_youtube_ids()
    logger.info(f"WordPress has {len(existing_youtube_ids)} article youtube_ids; syncing only missing")
    all_articles = deps.database.get_all_articles()
    to_sync = [
        a for a in all_articles
        if (a.get("youtube_id") or "").strip()
        and (a.get("youtube_id") or "").strip() not in existing_youtube_ids
    ]
    if limit is not None and limit > 0:
        to_sync = to_sync[:limit]
    db_youtube_ids = [(a.get("youtube_id") or "").strip() for a in all_articles if (a.get("youtube_id") or "").strip()]
    already_on_site = sum(1 for yid in db_youtube_ids if yid in existing_youtube_ids)
    if not to_sync:
        return {
            "success": True,
            "total_articles": len(all_articles),
            "already_on_site": already_on_site,
            "wordpress_youtube_ids_count": len(existing_youtube_ids),
            "synced": 0,
            "failed": 0,
            "errors": [],
            "message": "No missing articles to sync; all are already on WordPress.",
        }
    logger.info(f"Syncing {len(to_sync)} missing articles (skipping {already_on_site} already on site)")
    synced = 0
    failed = 0
    errors = []
    for article in to_sync:
        article_id = article.get("id")
        if not article_id:
            failed += 1
            errors.append({"article_id": None, "error": "Article missing ID field"})
            continue
        result = svc.sync_one_article(article_id)
        if result.get("success"):
            synced += 1
        else:
            failed += 1
            errors.append({"article_id": article_id, "error": result.get("error", "Unknown error")})
            logger.warning(f"Sync failed for article {article_id}: {result.get('error')}")
    return {
        "success": True,
        "total_articles": len(all_articles),
        "already_on_site": already_on_site,
        "wordpress_youtube_ids_count": len(existing_youtube_ids),
        "synced": synced,
        "failed": failed,
        "errors": errors,
        "message": f"Synced {synced} missing articles; {already_on_site} already on site.",
    }


def _normalize_text(s: Optional[str]) -> str:
    """Collapse whitespace for comparison; avoids false positives from formatting-only differences."""
    return " ".join((s or "").split())


def _normalize_for_compare(s: Optional[str]) -> str:
    """Unescape HTML entities then collapse whitespace so e.g. &amp; and & compare equal."""
    return _normalize_text(html.unescape(s or ""))


def _text_diff(a: str, b: str, fromfile: str = "wordpress", tofile: str = "fastapi", context_lines: int = 5) -> str:
    """Return a unified diff between two strings (e.g. title or content)."""
    a_lines = (a or "").splitlines(keepends=True) or [""]
    b_lines = (b or "").splitlines(keepends=True) or [""]
    diff = difflib.unified_diff(
        a_lines,
        b_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
        n=context_lines,
    )
    return "\n".join(diff)


def _diff_summary(a: str, b: str, max_snippets: int = 5, max_len: int = 120) -> List[str]:
    """Return a short list of what changed: WordPress lines vs FastAPI lines so you see the difference at a glance."""
    a_lines = (a or "").splitlines()
    b_lines = (b or "").splitlines()
    diff = difflib.unified_diff(a_lines, b_lines, fromfile="wp", tofile="db", lineterm="", n=0)
    diff_lines = list(diff)
    removed = [ln[1:].strip() for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")]
    added = [ln[1:].strip() for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")]
    snippets: List[str] = []
    for r in removed[:max_snippets]:
        r_short = (r[:max_len] + "…") if len(r) > max_len else r
        snippets.append(f"WordPress: {r_short!r}")
    for ad in added[:max_snippets]:
        ad_short = (ad[:max_len] + "…") if len(ad) > max_len else ad
        snippets.append(f"FastAPI:   {ad_short!r}")
    return snippets


@router.get("/wordpress/audit-sync-status")
def audit_sync_status(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """
    Audit sync status: compare WordPress (wp/v2/article) and FastAPI DB by youtube_id.
    Compares after normalizing whitespace and HTML entities (e.g. &amp; vs &) so encoding differences don't count.
    Returns full data for any post where title or content still differs.
    """
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    if not deps.wordpress_sync_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    wp_articles = deps.wordpress_sync_service.get_article_audit_data_from_wordpress()
    db_articles = deps.database.get_all_articles()
    db_by_youtube_id = {
        (a.get("youtube_id") or "").strip(): a
        for a in db_articles
        if (a.get("youtube_id") or "").strip()
    }
    in_both = 0
    discrepancies: list = []
    for item in wp_articles:
        youtube_id = (item.get("youtube_id") or "").strip()
        if not youtube_id or youtube_id not in db_by_youtube_id:
            continue
        in_both += 1
        db_article = db_by_youtube_id[youtube_id]
        wp_title = item.get("title") or ""
        wp_content = item.get("content") or ""
        db_title = db_article.get("title") or ""
        db_content = db_article.get("content") or ""
        title_mismatch = _normalize_for_compare(wp_title) != _normalize_for_compare(db_title)
        content_mismatch = _normalize_for_compare(wp_content) != _normalize_for_compare(db_content)
        if title_mismatch or content_mismatch:
            mismatch: List[str] = []
            diff_out: Dict[str, str] = {}
            summary_out: Dict[str, List[str]] = {}
            if title_mismatch:
                mismatch.append("title")
                diff_out["title_diff"] = _text_diff(wp_title, db_title)
                summary_out["title"] = _diff_summary(wp_title, db_title)
            if content_mismatch:
                mismatch.append("content")
                diff_out["content_diff"] = _text_diff(wp_content, db_content)
                summary_out["content"] = _diff_summary(wp_content, db_content)
            discrepancies.append({
                "youtube_id": youtube_id,
                "mismatch": mismatch,
                "diff_summary": summary_out,
                "diff": diff_out,
                "wordpress": {"post_id": item.get("post_id"), "title": wp_title, "content": wp_content},
                "fastapi": db_article,
            })
    return {
        "total_on_wordpress": len(wp_articles),
        "total_in_fastapi": len(db_articles),
        "in_both": in_both,
        "discrepancies_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
