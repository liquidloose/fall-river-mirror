"""WordPress sync endpoints."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies

router = APIRouter(tags=["wordpress"])
logger = logging.getLogger(__name__)


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
