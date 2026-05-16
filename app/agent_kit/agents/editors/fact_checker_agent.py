"""
Fact checker agent: returns a JSON fact-check report for article text (read-only).
"""
import json
import os
import re
import logging
from typing import Any, Dict

from fastapi.responses import JSONResponse

from app.agent_kit.utility_classes.text_llm_client import get_text_llm

logger = logging.getLogger(__name__)

ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE = "Article not found for this YouTube id"

_FACT_CHECK_SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "context_files", "fact_check_system.md"
)


class FactCheckerAgent:
    """Produces a structured fact-check report from title, bullet points, and content (no DB writes)."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self._llm = get_text_llm()

    def _build_system_prompt(self) -> str:
        with open(_FACT_CHECK_SYSTEM_PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()

    def _build_user_message(self, title: str, bullet_points: str, content: str) -> str:
        bullets_display = (bullet_points or "").strip()
        if not bullets_display:
            bullets_display = "(none)"
        return f"Title:\n{title}\n\nBullet points:\n{bullets_display}\n\nContent:\n{content}"

    def fact_check_by_youtube_id(self, youtube_id: str) -> Dict[str, Any]:
        yt = (youtube_id or "").strip()
        logger.info("Fact-check started for youtube_id=%s", yt)
        if not yt:
            return {
                "success": False,
                "message": "YouTube id is required",
                "youtube_id": youtube_id,
                "article_id": None,
                "report": None,
            }
        article = self._db.get_article_by_youtube_id(yt)
        if not article:
            logger.warning("Fact-check: no article for youtube_id=%s", yt)
            return {
                "success": False,
                "message": ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE,
                "youtube_id": yt,
                "article_id": None,
                "report": None,
            }
        article_id = article["id"]
        title = (article.get("title") or "").strip()
        content = article.get("content") or ""
        bullet_points = article.get("bullet_points") or ""
        logger.info(
            "Article loaded for fact-check: article_id=%s youtube_id=%s title_len=%s bullets_len=%s content_len=%s",
            article_id,
            yt,
            len(title),
            len(bullet_points or ""),
            len(content),
        )
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(title, bullet_points, content)
        try:
            logger.info("Calling AI for fact-check article_id=%s", article_id)
            out = self._llm.get_raw_response(system_prompt, user_message)
        except Exception as e:
            logger.exception("Fact checker: AI request raised for article_id=%s", article_id)
            return {
                "success": False,
                "message": f"AI request failed: {e!s}",
                "youtube_id": yt,
                "article_id": article_id,
                "report": None,
            }
        if isinstance(out, JSONResponse):
            try:
                body = out.body.decode("utf-8")
                err_payload = json.loads(body)
                err_msg = err_payload.get("error", body) or "Unknown error"
            except Exception:
                err_msg = "AI returned an error response"
            logger.warning("Fact checker: AI request failed for article_id=%s: %s", article_id, err_msg)
            return {
                "success": False,
                "message": f"AI request failed: {err_msg}",
                "youtube_id": yt,
                "article_id": article_id,
                "report": None,
            }
        logger.info("AI fact-check response received for article_id=%s", article_id)
        raw = (out or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                "Fact checker: invalid JSON for article_id=%s: %s",
                article_id,
                e,
                exc_info=True,
            )
            return {
                "success": False,
                "message": f"Invalid JSON from AI: {e!s}",
                "youtube_id": yt,
                "article_id": article_id,
                "report": None,
            }
        if not isinstance(data, dict):
            return {
                "success": False,
                "message": "AI response was not a JSON object",
                "youtube_id": yt,
                "article_id": article_id,
                "report": None,
            }
        return {
            "success": True,
            "message": "Fact-check complete",
            "youtube_id": yt,
            "article_id": article_id,
            "report": data,
        }
