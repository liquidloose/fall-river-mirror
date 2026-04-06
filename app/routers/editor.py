"""Editor endpoints: spell-check and correct official names in articles."""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.content_department.ai_editors import EditorAgent, FactCheckAgent

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


@router.post("/article/by-youtube/{youtube_id}/fact-check")
def fact_check_article(
    youtube_id: str,
    scope: Literal["article", "bullet_points"] = "article",
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Fact-check against transcript (look up by YouTube ID). Switch: scope=article (default) fact-checks title + content; scope=bullet_points fact-checks bullet points only."""
    logger.info("Fact-check requested for youtube_id=%s, scope=%s", youtube_id, scope)
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    article = db.get_article_by_youtube_id(youtube_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No article found for YouTube ID {youtube_id}",
        )
    article_id = article["id"]
    agent = FactCheckAgent(db)
    result = agent.fact_check(article_id, scope=scope)
    if not result["success"]:
        msg = result.get("message", "")
        if msg in ("Article has no linked transcript", "Transcript not found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
    logger.info("Fact-check completed for youtube_id=%s (article_id=%s): %s", youtube_id, article_id, result.get("message", "ok"))
    return {
        "success": result["success"],
        "message": result.get("message"),
        "youtube_id": article.get("youtube_id"),
        "title": article.get("title"),
        "report": result.get("report"),
    }


@router.post("/fact-check-batch")
def fact_check_batch(
    limit: Optional[int] = None,
    scope: Literal["article", "bullet_points"] = "article",
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run fact-check on multiple articles. Switch: scope=article (default) fact-checks title + content; scope=bullet_points fact-checks bullet points only. Optional limit caps how many to process. Skips articles without transcript_id."""
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    all_articles = db.get_all_articles()
    eligible = [a for a in all_articles if a.get("transcript_id")]
    if limit is not None and limit > 0:
        articles = eligible[:limit]
    else:
        articles = eligible
    processed = 0
    failed: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []
    agent = FactCheckAgent(db)
    logger.info("Fact-check batch started: processing %s articles (limit=%s, scope=%s)", len(articles), limit, scope)
    for article in articles:
        article_id = article.get("id")
        if not article_id:
            continue
        try:
            result = agent.fact_check(article_id, scope=scope)
            processed += 1
            if not result.get("success"):
                failed.append({"youtube_id": article.get("youtube_id"), "title": article.get("title"), "error": result.get("message", "Unknown error")})
            else:
                reports.append({"youtube_id": article.get("youtube_id"), "title": article.get("title"), "report": result.get("report")})
        except Exception as e:
            logger.exception("Fact-check batch failed for article_id=%s: %s", article_id, e)
            failed.append({"youtube_id": article.get("youtube_id"), "title": article.get("title"), "error": str(e)})
    logger.info("Fact-check batch completed: processed=%s, failed=%s", processed, len(failed))
    return {
        "success": True,
        "total_eligible": len(eligible),
        "processed": processed,
        "reports": reports,
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
