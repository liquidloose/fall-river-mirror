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
    scope: Literal["article", "bullet_points", "both"] = "both",
    order: Literal["asc", "desc"] = "desc",
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """
    Run fact-check on multiple articles, ordered by the WordPress ``_article_meeting_date`` custom field.

    Article data (title, content, bullet points) comes entirely from WordPress
    (``wp/v2/article`` with the theme's ``__frmCustomFieldFilter=_article_meeting_date``
    sort hook). The transcript is looked up from the local SQLite by ``youtube_id``,
    since transcripts are not stored on WordPress.

    - scope=both (default): fact-check title + content AND bullet points (one report per scope).
    - scope=article: fact-check title + content only.
    - scope=bullet_points: fact-check bullet points only.
    - order=desc (default): newest meeting first. order=asc: oldest meeting first.
    - limit: cap on how many articles to process. Applied to the WP-ordered listing.

    Each entry in ``reports`` and ``failed`` includes a ``scope`` field identifying which
    fact-check produced it ("article" or "bullet_points"); when scope=both, each article
    can produce up to two entries. Pre-flight failures (no transcript for the youtube_id)
    emit a single entry with the requested ``scope`` value.

    Articles with an empty ``_article_meeting_date`` are still returned by WordPress and
    sort to the end on DESC / start on ASC.
    """
    db = deps.database
    if not db:
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
    sub_scopes: List[Literal["article", "bullet_points"]] = (
        ["article", "bullet_points"] if scope == "both" else [scope]
    )
    wp_articles = svc.get_articles_sorted_by_meeting_date(order=order, limit=limit)
    processed = 0
    failed: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []
    agent = FactCheckAgent(db)
    logger.info(
        "Fact-check batch started: %s articles from WordPress (limit=%s, scope=%s, sub_scopes=%s, order=%s)",
        len(wp_articles), limit, scope, sub_scopes, order,
    )
    for wp_item in wp_articles:
        youtube_id = (wp_item.get("youtube_id") or "").strip()
        title = wp_item.get("title") or ""
        meeting_date = wp_item.get("meeting_date") or ""
        content = wp_item.get("content") or ""
        bullet_points = wp_item.get("bullet_points") or ""
        if not youtube_id:
            continue
        transcript_row = db.get_transcript_by_youtube_id(youtube_id)
        transcript_content = ""
        if transcript_row and len(transcript_row) > 3:
            transcript_content = (transcript_row[3] or "").strip()
        if not transcript_content:
            failed.append({
                "youtube_id": youtube_id,
                "title": title,
                "meeting_date": meeting_date,
                "scope": scope,
                "error": "No transcript for youtube_id",
            })
            continue
        log_label = f"youtube_id={youtube_id}"
        for sub_scope in sub_scopes:
            try:
                result = agent.fact_check_with_data(
                    title=title,
                    content=content,
                    bullet_points=bullet_points,
                    transcript_content=transcript_content,
                    scope=sub_scope,
                    log_label=log_label,
                )
                processed += 1
                if not result.get("success"):
                    failed.append({
                        "youtube_id": youtube_id,
                        "title": title,
                        "meeting_date": meeting_date,
                        "scope": sub_scope,
                        "error": result.get("message", "Unknown error"),
                    })
                else:
                    reports.append({
                        "youtube_id": youtube_id,
                        "title": title,
                        "meeting_date": meeting_date,
                        "scope": sub_scope,
                        "report": result.get("report"),
                    })
            except Exception as e:
                logger.exception(
                    "Fact-check batch failed for youtube_id=%s scope=%s: %s",
                    youtube_id, sub_scope, e,
                )
                failed.append({
                    "youtube_id": youtube_id,
                    "title": title,
                    "meeting_date": meeting_date,
                    "scope": sub_scope,
                    "error": str(e),
                })
    logger.info("Fact-check batch completed: processed=%s, failed=%s", processed, len(failed))
    return {
        "success": True,
        "scope": scope,
        "order": order,
        "total_from_wordpress": len(wp_articles),
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
