"""
Official-name spell-check editor (article title + HTML/plain body).

:class:`EditorAgent` loads an article, sends title and body to a text LLM with a
narrow task—fix spellings **only** for names listed in the official-names
guideline from
:func:`~app.agent_kit.utility_classes.official_names_loader.get_guideline_text`
(built from ``agent_kit/agents/editors/context_files/official_names.md``; same
canonical list FRJ1 uses). It does **not** rewrite for grammar, tone, factual
accuracy, or style beyond that constrained fix.

HTTP usage
==========

Typically constructed per request in :mod:`~app.routers.editor`:

- ``POST /editor/article/{article_id}/spell-check`` calls
  ``EditorAgent(...).spell_check_and_save(article_id)``.
- Batch spell-check loops the same method for unchecked articles.

The router may add keys such as ``wordpress_synced`` after a successful save;
this class returns only the envelope described below.

LLM wiring
==========

Uses :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery` with
``TextLLMProvider.XAI``. The process environment must expose the credentials and
model id expected by that client (currently ``XAI_API_KEY`` and ``XAI_MODEL``).

Flow
====

1. ``db.get_article_by_id`` → rows with ``title``, ``content`` or missing row.
2. Build system prompt embedding the guideline; user message is title + body.
3. ``get_raw_response`` — model must answer with a JSON object
   ``{"title": "...", "content": "..."}``. If the reply is wrapped in a Markdown
   fenced code block labeled ``json``, the fences are stripped before
   ``json.loads``.
4. Parsing falls back per field: absent ``title`` uses the loaded title;
   absent ``content`` keeps the loaded body unchanged.
5. If title and body match the originals, skip DB writes; still call
   ``update_article_spell_checked(..., True)``.
6. If either string changed, ``update_article_title`` then ``update_article_content``.
   Both must report success **before**
   ``update_article_spell_checked(..., True)``. If ``update_article_content``
   fails after title updated, the title change may already be persisted and
   ``spell_checked`` remains ``False``.

Database protocol
=================

``db`` must implement:

- ``get_article_by_id(article_id: int)`` → ``dict`` with ``title``, ``content``,
  or a falsy value when missing.
- ``update_article_title(article_id, title: str)`` → ``bool``
- ``update_article_content(article_id, content: str)`` → ``bool``
- ``update_article_spell_checked(article_id, True)`` — on every successful agent
  outcome (already correct copy or corrections committed).

Response envelope from ``spell_check_and_save``
==============================================

Every outcome includes:

- ``success`` ``bool``
- ``message`` ``str`` (human-readable; also used by HTTP layer for status)
- ``article_id`` ``int``
- ``original_title`` / ``original_content``
- ``corrected_title`` / ``corrected_content``

On failures before load, originals and corrected fields may be ``None``. On AI
or parse failures after load, ``corrected_*`` are typically ``None`` while
``original_*`` reflect stored copy. Successful runs always populate all four strings.

Failures
=========

- Missing article, LLM/network exceptions, :class:`fastapi.responses.JSONResponse`
  from the LLM layer, invalid JSON, or DB update errors → ``success`` is
  ``False``; ``update_article_spell_checked`` is **not** called except on the two
  success branches above.
"""
import json
import re
import logging
from typing import Any, Dict

from fastapi.responses import JSONResponse

from app.agent_kit.utility_classes.official_names_loader import get_guideline_text
from app.agent_kit.utility_classes.llm_text_query import LLMTextQuery
from app.data.enum_classes import TextLLMProvider

logger = logging.getLogger(__name__)


class EditorAgent:
    """
    LLM-assisted copy editor scoped to official name spellings.

    Holds a database accessor and an xAI-backed
    :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery`. Used by
    :mod:`~app.routers.editor` for spell-check endpoints. Behavioral contract and
    return shape are documented in this package's module docstring.

    See also:
        :func:`~app.agent_kit.utility_classes.official_names_loader.get_guideline_text`
            Source of canonical names inlined into prompts.
    """

    def __init__(self, db: Any) -> None:
        """
        Args:
            db: Object implementing the database protocol documented in this
                module's docstring.

        Notes:
            Instantiates :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery`
            with ``TextLLMProvider.XAI`` on each constructed agent (per HTTP request
            when used from the FastAPI router).
        """
        self._db = db
        self._llm = LLMTextQuery(provider=TextLLMProvider.XAI)

    def _build_system_prompt(self) -> str:
        """
        Compose the spell-check system message: Fall River Mirror role text plus
        the live official-names guideline from Markdown on disk.

        Returns:
            Full system prompt string passed as the LLM ``context`` / system
            instruction alongside the user payload in ``spell_check_and_save``.
        """
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
        Run the official-name spell-check pipeline for a single stored article.

        Persists corrections only when the model proposes different ``title``
        or ``content`` strings and both ``update_article_*`` calls succeed.

        Args:
            article_id: Primary key (or resolver) understood by ``db``.

        Returns:
            Envelope documented in this module docstring (
            ``success``, ``message``, ``article_id``, ``original_*``,
            ``corrected_*``). Successful ``message`` values are lowercase
            ``"no spelling errors discovered"`` when the model echoed input, or
            ``"Spelling corrections applied and saved"`` after both DB writes.

        Raises:
            This method catches LLM and DB exceptions and returns them inside
            the envelope instead of propagating.

        Warning:
            A failed ``update_article_content`` after a successful title update can
            leave the article with an updated title and ``spell_checked`` still
            false; callers may need remediation or retries.
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
            out = self._llm.get_raw_response(system_prompt, user_message)
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
