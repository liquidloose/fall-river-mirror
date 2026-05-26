"""Editor endpoints: fact-check articles and sync to WordPress.

Spell-check belongs to Gemma Nye's extractor pipeline (pass 4) now —
articles are written from spelling-clean anchors, so a post-hoc article
spell-check editor is no longer part of the system.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import TextLLMProvider
from app.agent_kit.agents.editors import FactCheckerAgent
from app.agent_kit.agents.editors.fact_checker_agent import (
    ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE,
)

router = APIRouter(prefix="/editor", tags=["editor"])
logger = logging.getLogger(__name__)


@router.post("/article/by-youtube/{youtube_id}/fact-check")
def fact_check_article_by_youtube(
    youtube_id: str,
    provider: TextLLMProvider = TextLLMProvider.XAI,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Return a JSON fact-check report for manual WordPress editing (read-only; no DB or WP updates).

    Query ``provider``: ``xai`` (default) or ``anthropic``. Requires ``XAI_API_KEY`` + ``XAI_MODEL``
    for xAI, or ``ANTHROPIC_API_KEY`` (+ optional ``ANTHROPIC_MODEL``) for Anthropic. Response
    includes ``provider`` and ``model`` echoing the backend and model id used.
    """
    logger.info(
        "Fact-check requested for youtube_id=%s provider=%s",
        youtube_id,
        provider.value,
    )
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    agent = FactCheckerAgent(db, provider=provider)
    result = agent.fact_check_by_youtube_id(youtube_id)
    if not result["success"] and result.get("message") == ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No article found for YouTube id {result.get('youtube_id', youtube_id)!r}",
        )
    if not result["success"] and result.get("message") == "YouTube id is required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YouTube id is required",
        )
    logger.info(
        "Fact-check finished for youtube_id=%s provider=%s model=%s success=%s message=%s",
        youtube_id,
        result.get("provider"),
        result.get("model"),
        result.get("success"),
        result.get("message", "ok"),
    )
    return result


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
