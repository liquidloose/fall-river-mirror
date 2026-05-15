"""Editor endpoints: spell-check and correct official names in articles."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.content_department.ai_editors import EditorAgent

router = APIRouter(prefix="/editor", tags=["editor"])
logger = logging.getLogger(__name__)


@router.post("/article/{article_id}/spell-check")
def spell_check_article(
    article_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Spell-check article title and content against official names; persist corrections to the database."""
    logger.info("Spell-check requested for article_id=%s", article_id)
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    editor = EditorAgent(db)
    result = editor.spell_check_and_save(article_id)
    if not result["success"] and result.get("message") == "Article not found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found",
        )
    # If we saved corrections to the DB, push the updated title/content to WordPress
    if result["success"] and result.get("message") == "Spelling corrections applied and saved":
        svc = deps.wordpress_sync_service
        if svc:
            wp_result = svc.update_article_title_and_content(article_id)
            result["wordpress_synced"] = wp_result.get("success", False)
            if not wp_result.get("success"):
                result["wordpress_error"] = wp_result.get("error", "Unknown error")
                logger.warning(
                    "Spell-check saved to DB but WordPress update failed for article_id=%s: %s",
                    article_id,
                    result.get("wordpress_error"),
                )
            else:
                logger.info("Spell-check: DB and WordPress updated for article_id=%s", article_id)
        else:
            result["wordpress_synced"] = False
            result["wordpress_error"] = "WordPress sync service not available"
    logger.info(
        "Spell-check completed for article_id=%s: %s",
        article_id,
        result.get("message", "ok"),
    )
    return result


@router.post("/spell-check-batch")
def spell_check_batch(
    limit: Optional[int] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run spell-check on multiple articles. Optional limit caps how many to process (default: all)."""
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    all_articles = db.get_all_articles()
    # Only process articles that have not already been spell-checked
    unchecked = [a for a in all_articles if not a.get("spell_checked")]
    if limit is not None and limit > 0:
        articles = unchecked[:limit]
    else:
        articles = unchecked
    total_available = len(all_articles)
    processed = 0
    corrections_applied = 0
    no_errors_count = 0
    wordpress_synced_count = 0
    failed: List[Dict[str, Any]] = []

    editor = EditorAgent(db)
    svc = deps.wordpress_sync_service

    logger.info("Spell-check batch started: processing %s articles (limit=%s)", len(articles), limit)
    for article in articles:
        article_id = article.get("id")
        if not article_id:
            continue
        try:
            result = editor.spell_check_and_save(article_id)
            processed += 1
            if not result.get("success"):
                failed.append({"article_id": article_id, "error": result.get("message", "Unknown error")})
                continue
            if result.get("message") == "Spelling corrections applied and saved":
                corrections_applied += 1
                if svc:
                    wp_result = svc.update_article_title_and_content(article_id)
                    if wp_result.get("success"):
                        wordpress_synced_count += 1
            else:
                no_errors_count += 1
        except Exception as e:
            logger.exception("Spell-check batch failed for article_id=%s: %s", article_id, e)
            failed.append({"article_id": article_id, "error": str(e)})

    already_checked = total_available - len(unchecked)
    logger.info(
        "Spell-check batch completed: processed=%s, corrections=%s, no_errors=%s, wp_synced=%s, failed=%s, already_checked=%s",
        processed,
        corrections_applied,
        no_errors_count,
        wordpress_synced_count,
        len(failed),
        already_checked,
    )
    return {
        "success": True,
        "total_available": total_available,
        "already_checked": already_checked,
        "processed": processed,
        "corrections_applied": corrections_applied,
        "no_errors_count": no_errors_count,
        "wordpress_synced_count": wordpress_synced_count,
        "failed_count": len(failed),
        "failed": failed,
    }


@router.post("/article/{article_id}/swap-to-wordpress")
def swap_article_to_wordpress(
    article_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Send this article's current title and content from the database to WordPress (update only; no slug change, no delete)."""
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
    result = svc.update_article_title_and_content(article_id)
    if not result["success"]:
        raise HTTPException(
            status_code=result.get("http_status", status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=result.get("error", "Swap to WordPress failed"),
        )
    return result
