"""
Fact-check helper for articles resolved by YouTube video id.

:class:`FactCheckerAgent` loads ``title``, ``bullet_points``, and ``content`` from the
database, sends them to the configured text LLM with instructions from
``context_files/fact_check_system.md``, and parses the model reply as JSON.

**Does not** persist reports or mutate articles; callers consume the returned dict only.

**Flow**

1. ``get_article_by_youtube_id(youtube_id)`` → article row or missing.
2. Build system prompt from ``fact_check_system.md``; user message bundles title,
   bullets (or ``(none)``), and body.
3. ``LLMTextQuery(...).get_raw_response`` — expect a JSON **object**; markdown fences
   stripped when present.
4. Return envelope ``success``, ``message``, ``youtube_id``, ``article_id``, ``provider``,
   ``model``, ``report``.

**Database object** (``db`` passed to the constructor) must provide:

- ``get_article_by_youtube_id(youtube_id)`` → dict with ``id``, ``title``, ``content``,
  ``bullet_points`` (values may be empty strings), or ``None``

On validation or AI failures, ``success`` is ``False``, ``report`` is ``None``, and
``message`` describes the issue. ``JSONResponse`` from the LLM layer is handled like a failed request.
"""
import json
import os
import re
import logging
from typing import Any, Dict

from fastapi.responses import JSONResponse

from app.agent_kit.utility_classes.llm_text_query import LLMTextQuery
from app.data.enum_classes import TextLLMProvider

logger = logging.getLogger(__name__)

# Returned in ``fact_check_by_youtube_id`` when ``db.get_article_by_youtube_id`` finds no row.
ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE = "Article not found for this YouTube id"

_FACT_CHECK_SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "context_files", "fact_check_system.md"
)


class FactCheckerAgent:
    """
    Read-only LLM fact-check over article fields keyed by YouTube id.

    Constructor accepts ``provider`` (:class:`~app.data.enum_classes.TextLLMProvider`) to
    select xAI or Anthropic. Every response envelope includes ``provider`` and ``model``
    from :meth:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery.llm_metadata`.

    See module docstring for required ``db`` methods and return envelope.
    """

    def __init__(
        self,
        db: Any,
        provider: TextLLMProvider = TextLLMProvider.XAI,
    ) -> None:
        self._db = db
        self._llm = LLMTextQuery(provider=provider)

    def _envelope(self, **fields: Any) -> Dict[str, Any]:
        return {**self._llm.llm_metadata(), **fields}

    def _build_system_prompt(self) -> str:
        """Full text of ``fact_check_system.md`` (model instructions and JSON schema)."""
        with open(_FACT_CHECK_SYSTEM_PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()

    def _build_user_message(self, title: str, bullet_points: str, content: str) -> str:
        """Single user message carrying title, bullets (or ``(none)``), and body."""
        bullets_display = (bullet_points or "").strip()
        if not bullets_display:
            bullets_display = "(none)"
        return f"Title:\n{title}\n\nBullet points:\n{bullets_display}\n\nContent:\n{content}"

    def fact_check_by_youtube_id(self, youtube_id: str) -> Dict[str, Any]:
        """
        Look up an article by YouTube id and return an envelope plus optional parsed report.

        **Normalization.** The lookup uses ``youtube_id.strip()`` (empty after strip → validation error).
        Successful responses echo the stripped id as ``youtube_id``. On "required" failure,
        ``youtube_id`` is whatever was passed in (may differ from ``yt``), ``article_id`` is ``None``.

        **Early exits** (no LLM call), all with ``report=None``:

        - Blank id → ``success=False``, ``message`` explains requirement.
        - ``db.get_article_by_youtube_id`` missing → ``success=False``,
          ``message`` set to ``ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE``.

        **LLM path.** Builds prompts via ``_build_system_prompt`` / ``_build_user_message``, then
        ``self._llm.get_raw_response``. Any exception becomes ``success=False`` and ``message``
        prefixed with ``AI request failed:``.

        **Transport errors.** Some clients return ``JSONResponse`` instead of raising; that is treated
        as failure: body is decoded, optional JSON ``error`` field becomes ``message`` detail.

        **Parsing.** Model output must be a UTF-8 string coerced to trimmed text, then ``json.loads``.

        - If the response starts with markdown code fences (optional ``json`` language tag),
          leading and trailing fences are stripped before parse (models often wrap JSON in markdown).
        - Parse errors → ``success=False``, ``Invalid JSON from AI: …``.
        - Top-level value **must be a JSON object** (``dict``); arrays or scalars →
          ``AI response was not a JSON object``.

        **Success.** ``success=True``, ``message="Fact-check complete"``, ``report`` is the parsed
        object. Field meanings (``overall_risk``, ``flags``, etc.) are defined in
        ``context_files/fact_check_system.md``. This method **never** writes to ``db``.

        All envelopes include ``provider`` and ``model`` (intended backend and model id from env).
        """
        yt = (youtube_id or "").strip()
        logger.info("Fact-check started for youtube_id=%s", yt)
        if not yt:
            return self._envelope(
                success=False,
                message="YouTube id is required",
                youtube_id=youtube_id,
                article_id=None,
                report=None,
            )
        article = self._db.get_article_by_youtube_id(yt)
        if not article:
            logger.warning("Fact-check: no article for youtube_id=%s", yt)
            return self._envelope(
                success=False,
                message=ARTICLE_NOT_FOUND_FOR_YOUTUBE_ID_MESSAGE,
                youtube_id=yt,
                article_id=None,
                report=None,
            )
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
            return self._envelope(
                success=False,
                message=f"AI request failed: {e!s}",
                youtube_id=yt,
                article_id=article_id,
                report=None,
            )
        if isinstance(out, JSONResponse):
            try:
                body = out.body.decode("utf-8")
                err_payload = json.loads(body)
                err_msg = err_payload.get("error", body) or "Unknown error"
            except Exception:
                err_msg = "AI returned an error response"
            logger.warning("Fact checker: AI request failed for article_id=%s: %s", article_id, err_msg)
            return self._envelope(
                success=False,
                message=f"AI request failed: {err_msg}",
                youtube_id=yt,
                article_id=article_id,
                report=None,
            )
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
            return self._envelope(
                success=False,
                message=f"Invalid JSON from AI: {e!s}",
                youtube_id=yt,
                article_id=article_id,
                report=None,
            )
        if not isinstance(data, dict):
            return self._envelope(
                success=False,
                message="AI response was not a JSON object",
                youtube_id=yt,
                article_id=article_id,
                report=None,
            )
        return self._envelope(
            success=True,
            message="Fact-check complete",
            youtube_id=yt,
            article_id=article_id,
            report=data,
        )
