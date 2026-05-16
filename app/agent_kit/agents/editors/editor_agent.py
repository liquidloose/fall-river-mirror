"""
Official-name spell-check editor (article title + HTML/plain body).

This module implements :class:`EditorAgent`, which loads an article from the
database, asks the LLM to correct **only** misspellings of canonical names from
:func:`~app.agent_kit.utility_classes.official_names_loader.get_guideline_text` (source document:
``agent_kit/agents/editors/context_files/official_names.md``, same text FRJ1 uses),

**Flow**

1. ``get_article_by_id`` → ``title``, ``content``
2. Build system prompt embedding the official-names guideline; user message is
   title + content.
3. ``XAITextQuery.get_raw_response`` — expect a JSON object
   ``{"title": "...", "content": "..."}`` (markdown fences stripped if present).
4. If text is unchanged, no title/content updates; still mark spell-check done.
5. If text changed, ``update_article_title`` then ``update_article_content``;
   both must succeed before marking spell-check done.

**Database object** (``db`` passed to the constructor) must provide:

- ``get_article_by_id(article_id)`` → dict with ``title``, ``content`` or ``None``
- ``update_article_title(article_id, title)`` → ``bool``
- ``update_article_content(article_id, content)`` → ``bool``
- ``update_article_spell_checked(article_id, True)`` — called whenever the run
  finishes successfully (including "no spelling errors discovered")

Errors from the model (``JSONResponse``), non-JSON output, or DB failures return
``success: False`` with a ``message`` and leave spell-check state unchanged except
where documented above.
"""
import json
import re
import logging
from typing import Any, Dict

from fastapi.responses import JSONResponse

from app.agent_kit.utility_classes.official_names_loader import get_guideline_text
from app.agent_kit.utility_classes.xai_text_query import XAITextQuery

logger = logging.getLogger(__name__)


class EditorAgent:
    """
    LLM-assisted copy editor scoped to official name spellings.

    Uses the same canonical name list as journalist prompts (see
    :func:`~app.agent_kit.utility_classes.official_names_loader.get_guideline_text`). Does not run
    general-purpose grammar or style edits.
    """

    def __init__(self, db: Any) -> None:
        """
        Args:
            db: Object implementing the contract described in this package's
                module docstring (article fetch/update + spell-checked flag).
        """
        self._db = db
        self._xai = XAITextQuery()

    def _build_system_prompt(self) -> str:
        """Assemble the editor system prompt including the official-names block."""
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
        Run the official-name spell-check pipeline for one article.

        On **every** successful completion (including when copy is already
        correct), ``update_article_spell_checked(article_id, True)`` is called.
        Title and content columns are updated only when the model returns
        different strings and both updates succeed.

        Returns:
            A dict always including ``success`` (bool), ``message`` (str),
            ``article_id`` (int), and the four title/content fields
            (``original_*`` / ``corrected_*``; originals set on error paths where
            the article was loaded). Typical ``message`` values include
            ``"no spelling errors discovered"``, ``"Spelling corrections applied and saved"``,
            ``"Article not found"``, or an error detail string from AI/DB/JSON parsing.
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
