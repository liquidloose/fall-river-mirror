"""
Editor agent: spell-check article title and content against official names,
then persist corrections to the database.
"""
import json
import re
import logging
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from app.data.official_names_loader import get_guideline_text
from app.content_department.creation_tools.xai_text_query import XAITextQuery

logger = logging.getLogger(__name__)


class EditorAgent:
    """
    Spell-checks article title and content against the canonical official names
    (same list as FRJ1). When misspellings are found, corrects and saves to the DB.
    """

    def __init__(self, db: Any) -> None:
        """
        Args:
            db: Database-like object with get_article_by_id, update_article_title, update_article_content.
        """
        self._db = db
        self._xai = XAITextQuery()

    def _build_system_prompt(self) -> str:
        guideline = get_guideline_text()
        return f"""You are a copy editor for Fall River Mirror.

TASK: Spell-check the given article title and content against the official names list below. Fix any misspellings of those names; leave everything else unchanged.

OFFICIAL NAMES (canonical spellings):

{guideline}

RULES:
- Only fix names/titles that appear in the list above but are misspelled in the text. Use the exact spelling from the list.
- Do NOT change anything else: no wording, no HTML, no punctuation. Keep the title and content identical except for corrected name spellings.
- Do NOT flag or change: "minor", "major", "May" (month), "motor", "Mason" (street), "McDonald's", or generic "mayor" when not referring to the person.

OUTPUT FORMAT: Return ONLY a single JSON object, no other text:
{{"title": "<corrected title>", "content": "<corrected content>"}}

Return the full title and full content; only the spellings of official names may differ from the input."""

    def spell_check_and_save(self, article_id: int) -> Dict[str, Any]:
        """
        Load article by id, spell-check title and content against official names,
        persist corrections to the DB when needed, and return a result dict.

        Returns:
            Dict with: success (bool), message (str), article_id (int),
            original_title, original_content, corrected_title, corrected_content (when applicable).
            When no spelling errors: message is "no spelling errors discovered" and DB is not updated.
        """
        logger.info("Spell-check started for article_id=%s", article_id)
        article = self._db.get_article_by_id(article_id)
        if not article:
            logger.warning("Spell-check article not found: article_id=%s", article_id)
            return {
                "success": False,
                "message": "Article not found",
                "article_id": article_id,
                "original_title": None,
                "original_content": None,
                "corrected_title": None,
                "corrected_content": None,
            }
        title = (article.get("title") or "").strip()
        content = article.get("content") or ""
        logger.info(
            "Article loaded for spell-check: article_id=%s, title_len=%s, content_len=%s",
            article_id,
            len(title),
            len(content),
        )
        system_prompt = self._build_system_prompt()
        user_message = f"Title:\n{title}\n\nContent:\n{content}"
        try:
            logger.info("Calling AI for spell-check article_id=%s", article_id)
            out = self._xai.get_raw_response(system_prompt, user_message)
        except Exception as e:
            logger.exception("Editor agent: AI request raised an exception for article_id=%s", article_id)
            return {
                "success": False,
                "message": f"AI request failed: {e!s}",
                "article_id": article_id,
                "original_title": title,
                "original_content": content,
                "corrected_title": None,
                "corrected_content": None,
            }
        if isinstance(out, JSONResponse):
            try:
                body = out.body.decode("utf-8")
                err_payload = json.loads(body)
                err_msg = err_payload.get("error", body) or "Unknown error"
            except Exception:
                err_msg = "AI returned an error response"
            logger.warning("Editor agent: AI request failed for article_id=%s: %s", article_id, err_msg)
            return {
                "success": False,
                "message": f"AI request failed: {err_msg}",
                "article_id": article_id,
                "original_title": title,
                "original_content": content,
                "corrected_title": None,
                "corrected_content": None,
            }
        logger.info("AI spell-check response received for article_id=%s", article_id)
        raw = (out or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            data = json.loads(raw)
            corrected_title = (data.get("title") or title).strip()
            corrected_content = data.get("content")
            if corrected_content is None:
                corrected_content = content
        except json.JSONDecodeError as e:
            logger.warning(
                "Editor agent: AI response was not valid JSON for article_id=%s: %s",
                article_id,
                e,
                exc_info=True,
            )
            return {
                "success": False,
                "message": f"Invalid JSON from AI: {e!s}",
                "article_id": article_id,
                "original_title": title,
                "original_content": content,
                "corrected_title": None,
                "corrected_content": None,
            }
        if corrected_title == title and corrected_content == content:
            logger.info(
                "Spell-check complete for article_id=%s: no spelling errors discovered",
                article_id,
            )
            self._db.update_article_spell_checked(article_id, True)
            return {
                "success": True,
                "message": "no spelling errors discovered",
                "article_id": article_id,
                "original_title": title,
                "original_content": content,
                "corrected_title": corrected_title,
                "corrected_content": corrected_content,
            }
        logger.info(
            "Spell-check found corrections for article_id=%s; persisting to database",
            article_id,
        )
        try:
            ok_title = self._db.update_article_title(article_id, corrected_title)
            if not ok_title:
                logger.warning("Editor agent: update_article_title returned False for article_id=%s", article_id)
                return {
                    "success": False,
                    "message": "Database refused to update article title",
                    "article_id": article_id,
                    "original_title": title,
                    "original_content": content,
                    "corrected_title": corrected_title,
                    "corrected_content": corrected_content,
                }
            ok_content = self._db.update_article_content(article_id, corrected_content)
            if not ok_content:
                logger.warning("Editor agent: update_article_content returned False for article_id=%s", article_id)
                return {
                    "success": False,
                    "message": "Database refused to update article content",
                    "article_id": article_id,
                    "original_title": title,
                    "original_content": content,
                    "corrected_title": corrected_title,
                    "corrected_content": corrected_content,
                }
        except Exception as e:
            logger.exception(
                "Editor agent: database update failed for article_id=%s: %s",
                article_id,
                e,
            )
            return {
                "success": False,
                "message": f"Database update failed: {e!s}",
                "article_id": article_id,
                "original_title": title,
                "original_content": content,
                "corrected_title": corrected_title,
                "corrected_content": corrected_content,
            }
        logger.info(
            "Spell-check complete for article_id=%s: corrections saved to database",
            article_id,
        )
        self._db.update_article_spell_checked(article_id, True)
        return {
            "success": True,
            "message": "Spelling corrections applied and saved",
            "article_id": article_id,
            "original_title": title,
            "original_content": content,
            "corrected_title": corrected_title,
            "corrected_content": corrected_content,
        }
