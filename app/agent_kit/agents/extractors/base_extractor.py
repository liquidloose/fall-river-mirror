"""
Base class for AI extractors — Gemini-backed agents that read source material
(meeting transcripts, video metadata, articles) and emit structured JSON for
downstream RAG indexing, fact retrieval, or as enriched context for prose
journalists.

Extractors are pinned to :attr:`TextLLMProvider.GEMINI` via
:attr:`BaseExtractor.PROVIDER`. Gemini's long-context window and
needle-in-haystack retrieval are the workload extractors are built around, so
the provider is a class attribute, not a constructor argument. If a future
extractor genuinely needs a different backend, override ``PROVIDER`` on the
subclass — but the design assumption is that all extractors are Gemini.

Two-prompt design (Gemini-native shape):

Gemini's API takes the system instruction as a top-level field separate from
the conversation contents, unlike OpenAI's flat ``messages: [{role, content}]``
list. This base class mirrors that shape by loading the two pieces from two
separate markdown files:

- :meth:`BaseExtractor.get_system_instruction` reads
  ``context_files/system_instructions/{first}_{last}_system_instructions.md``
  — the behavioral guardrails: extraction rules, accuracy constraints, output
  field semantics. Stable across calls.
- :meth:`BaseExtractor.get_user_prompt_template` reads
  ``context_files/user_prompts/{first}_{last}_user_prompt.md`` — the per-call
  payload template with ``{placeholder}`` substitution points (meeting
  metadata, transcript, etc.). :meth:`_render_user_prompt` performs literal
  ``str.replace`` substitution so transcripts containing stray ``{`` / ``}``
  characters do not crash ``str.format``.

Subclasses implement their own ``extract(...)`` with whatever domain-specific
signature makes sense (transcript + metadata for ``GemmaNye``, video URL for a
future video extractor, etc.) and delegate to :meth:`_render_user_prompt` +
:meth:`_call_llm_and_parse` for the shared plumbing.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from fastapi.responses import JSONResponse

from app.agent_kit.utility_classes.llm_text_query import LLMTextQuery
from app.data.enum_classes import TextLLMProvider

from ..base_creator import BaseCreator

logger = logging.getLogger(__name__)


class BaseExtractor(BaseCreator):
    """
    Base class for AI extractors. Pinned to Gemini; two-prompt (system + user) shape.

    Required class attributes (must be set by subclasses):

    - ``FIRST_NAME``, ``LAST_NAME``, ``FULL_NAME``, ``NAME`` — inherited from
      ``BaseCreator``; drive bio / description / prompt-file resolution under
      ``agent_kit/agents/extractors/context_files/``.
    - ``SLANT`` and ``STYLE`` — required by ``BaseCreator``. For extractors
      these describe **methodology** (e.g. ``SLANT = "neutral"``,
      ``STYLE = "structured"``), not political angle or prose voice.

    Required content files (per subclass, keyed by lowercased first/last name):

    - ``context_files/bios/{first}_{last}_bio.md``
    - ``context_files/descriptions/{first}_{last}_description.md``
    - ``context_files/system_instructions/{first}_{last}_system_instructions.md``
    - ``context_files/user_prompts/{first}_{last}_user_prompt.md``

    Public API: subclasses implement ``extract(...)`` with whatever argument
    shape their domain needs. The shared plumbing
    (:meth:`_render_user_prompt`, :meth:`_call_llm_and_parse`) is provider- and
    response-shape agnostic; only the markdown content varies per subclass.
    """

    CONTEXT_FILES_ROLE: ClassVar[Optional[str]] = "extractors"

    # Extractors are pinned to Gemini. Override on a subclass only if you genuinely
    # need a different backend — the rest of the design assumes long-context Gemini.
    PROVIDER: ClassVar[TextLLMProvider] = TextLLMProvider.GEMINI

    # Subdirectory + filename-suffix conventions for the two prompt files.
    # Mirror the bios/descriptions pattern from BaseCreator (``{name}_bio.md`` etc.).
    SYSTEM_INSTRUCTION_SUBDIR: ClassVar[str] = "system_instructions"
    SYSTEM_INSTRUCTION_FILENAME_SUFFIX: ClassVar[str] = "_system_instructions.md"
    USER_PROMPT_SUBDIR: ClassVar[str] = "user_prompts"
    USER_PROMPT_FILENAME_SUFFIX: ClassVar[str] = "_user_prompt.md"

    def get_personality(self) -> Dict[str, Any]:
        """Return the extractor's persona dict. Extractors have no tone/article-type."""
        return self.get_base_personality()

    def get_full_profile(self) -> Dict[str, Any]:
        """Return a serializable profile of this extractor for API/UI consumers."""
        return {
            "name": self.FULL_NAME,
            "first_name": self.FIRST_NAME,
            "last_name": self.LAST_NAME,
            "bio": self.get_bio(),
            "description": self.get_description(),
            "slant": self.SLANT,
            "style": self.STYLE,
        }

    def load_context(self, base_path: Optional[str] = None) -> str:
        """
        Extractors do not compose context from tone/slant/style markdown the way
        journalists do — guidance is fully captured by the system-instruction
        markdown loaded via :meth:`get_system_instruction`. Returns empty string.
        """
        return ""

    def get_system_instruction(self) -> str:
        """
        Load this extractor's system-instruction markdown.

        Reads
        ``context_files/system_instructions/{first}_{last}_system_instructions.md``.
        The returned text is passed as the **system_instruction** argument to
        the Gemini API (top-level, separate from the user message).

        Returns:
            Stripped file contents on success; empty string with a warning log
            when the file is not found.
        """
        return self._load_named_prompt(
            self.SYSTEM_INSTRUCTION_SUBDIR,
            self.SYSTEM_INSTRUCTION_FILENAME_SUFFIX,
        )

    def get_user_prompt_template(self) -> str:
        """
        Load this extractor's user-prompt template markdown.

        Reads
        ``context_files/user_prompts/{first}_{last}_user_prompt.md``.
        The returned text contains ``{placeholder}`` substitution points that
        :meth:`_render_user_prompt` fills with runtime values before the call.

        Returns:
            Stripped file contents on success; empty string with a warning log
            when the file is not found.
        """
        return self._load_named_prompt(
            self.USER_PROMPT_SUBDIR,
            self.USER_PROMPT_FILENAME_SUFFIX,
        )

    def _load_named_prompt(self, subdir: str, filename_suffix: str) -> str:
        """
        Shared markdown loader keyed by ``FIRST_NAME`` / ``LAST_NAME`` — same
        naming convention as :meth:`BaseCreator.get_bio` and
        :meth:`BaseCreator.get_description`.

        Args:
            subdir: Subdirectory under each context search base
                (e.g. ``"system_instructions"`` or ``"user_prompts"``).
            filename_suffix: Suffix appended to ``{first}_{last}`` to form the
                filename (e.g. ``"_system_instructions.md"``).
        """
        filename = (
            f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}{filename_suffix}"
        )
        last_tried = ""
        for base in self._context_search_bases():
            path = os.path.join(base, subdir, filename)
            last_tried = path
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except FileNotFoundError:
                continue
            except OSError as e:
                logger.warning(f"{self.FULL_NAME}: failed to read {path}: {e}")
                return ""
        if not last_tried:
            logger.warning(
                f"{self.FULL_NAME}: prompt lookup attempted but CONTEXT_FILES_ROLE is unset"
            )
            return ""
        logger.warning(f"{self.FULL_NAME}: prompt file not found at {last_tried}")
        return ""

    def _render_user_prompt(self, **kwargs: Any) -> str:
        """
        Substitute ``{key}`` occurrences in the user prompt template using
        literal :meth:`str.replace` (not :meth:`str.format`).

        Literal replacement is deliberate: transcripts and other free-form
        source text routinely contain stray ``{`` / ``}`` characters that would
        crash ``str.format``. ``None`` values are rendered as the literal
        string ``"null"`` for JSON-friendliness; everything else is ``str()``.

        Returns:
            The rendered user message ready to send to the LLM as the user
            (``contents``) payload.
        """
        template = self.get_user_prompt_template()
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            rendered_value = "null" if value is None else str(value)
            template = template.replace(placeholder, rendered_value)
        return template

    EXTRACTION_LOG_DIR: ClassVar[Path] = Path("logs") / "extractions"

    def _call_llm_and_parse(
        self,
        system_instruction: str,
        user_message: str,
        *,
        youtube_video_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Shared LLM-call + JSON-parse plumbing for all extractors.

        Constructs an :class:`LLMTextQuery` pinned to
        :attr:`BaseExtractor.PROVIDER` (Gemini by default), sends
        ``system_instruction`` and ``user_message`` as the two-prompt
        Gemini-shape inputs, strips markdown code fences when present, parses
        the response as JSON, and wraps everything in a result envelope that
        includes ``provider``, ``model``, and ``run_id`` metadata. Every call
        emits a JSON debug log file under :attr:`EXTRACTION_LOG_DIR` before
        returning, regardless of success or failure.

        Args:
            system_instruction: Behavioral guardrails / extraction rules,
                typically loaded via :meth:`get_system_instruction`.
            user_message: Per-call payload, typically rendered via
                :meth:`_render_user_prompt`.
            youtube_video_id: Identity of the source meeting for log-file
                naming and traceability. Recommended but optional; when
                absent the filename uses ``"unknown"`` in its place.

        Returns:
            ``{"provider", "model", "run_id", "success", "message", "data"}``.

            ``run_id`` is a fresh UUID per call and is the FK that callers
            stamp onto ``anchors`` rows when persisting the result.

            - On success: ``success=True``, ``data`` is the parsed JSON object,
              ``message="Extraction complete"``.
            - On LLM failure (exception or ``JSONResponse`` from the helper):
              ``success=False``, ``data=None``, ``message`` describes the
              error. The Gemini integration is not yet wired up, so all calls
              currently fall into this branch with a 501-shaped error.
            - On JSON-parse failure: ``success=False``, ``data=None``,
              ``message`` quotes the ``json.JSONDecodeError``.
            - When the parsed value is not a JSON object: ``success=False``,
              ``data=None``, ``message`` explains.
        """
        run_id = str(uuid.uuid4())
        llm = LLMTextQuery(provider=self.PROVIDER)
        meta = llm.llm_metadata()
        started_at = datetime.now(timezone.utc).isoformat()

        result_success = False
        result_message = ""
        result_data: Optional[Dict[str, Any]] = None
        parse_status = "success"
        error: Optional[str] = None
        raw_response: Any = None
        raw_text: Optional[str] = None

        try:
            raw = llm.get_raw_response(system_instruction, user_message)
        except Exception as e:
            logger.exception(f"{self.FULL_NAME}: LLM call raised")
            parse_status = "api_error"
            error = f"LLM request failed: {e!s}"
            result_message = error
        else:
            if isinstance(raw, JSONResponse):
                try:
                    body = raw.body.decode("utf-8")
                    err = json.loads(body).get("error", body) or "Unknown LLM error"
                except Exception:
                    err = "LLM returned an error response"
                logger.warning(
                    f"{self.FULL_NAME}: LLM returned error envelope: {err}"
                )
                parse_status = "api_error"
                error = f"LLM request failed: {err}"
                result_message = error
            else:
                raw_text = (raw or "").strip()
                text = raw_text
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```\s*$", "", text)
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.warning(f"{self.FULL_NAME}: invalid JSON from LLM: {e}")
                    parse_status = "parse_error"
                    error = f"Invalid JSON from LLM: {e!s}"
                    result_message = error
                else:
                    raw_response = data
                    if not isinstance(data, dict):
                        parse_status = "shape_error"
                        error = "LLM response was not a JSON object"
                        result_message = error
                    else:
                        parse_status = "success"
                        result_success = True
                        result_message = "Extraction complete"
                        result_data = data

        completed_at = datetime.now(timezone.utc).isoformat()

        # On parse_error we still want the raw text in the log so it can be
        # pasted back into Gemini chat for debugging the prompt.
        log_raw = raw_response if raw_response is not None else raw_text
        log_path = self._write_extraction_log(
            {
                "run_id": run_id,
                "youtube_video_id": youtube_video_id,
                "extractor_name": self.FULL_NAME,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "started_at": started_at,
                "completed_at": completed_at,
                "system_instruction": system_instruction,
                "user_message": user_message,
                "raw_response": log_raw,
                "parse_status": parse_status,
                "error": error,
            }
        )

        if result_success and isinstance(result_data, dict):
            factual_count = len(result_data.get("factual_anchor_items") or [])
            bullet_count = len(result_data.get("executive_summary_bullets") or [])
            logger.info(
                "%s: extraction succeeded yt=%s run_id=%s "
                "factual_anchors=%d summary_bullets=%d log=%s",
                self.FULL_NAME,
                youtube_video_id or "unknown",
                run_id,
                factual_count,
                bullet_count,
                log_path if log_path is not None else "(log write failed)",
            )

        return {
            **meta,
            "run_id": run_id,
            "success": result_success,
            "message": result_message,
            "data": result_data,
        }

    def _write_extraction_log(self, payload: Dict[str, Any]) -> Optional[Path]:
        """
        Write a per-call JSON debug log under :attr:`EXTRACTION_LOG_DIR`.

        Filename pattern: ``{utc_iso_ts}_yt{youtube_video_id}_r{run_id}.json``
        where ``:`` characters in the timestamp are replaced with ``-`` for
        cross-platform filesystem safety. When ``youtube_video_id`` is
        missing, the literal string ``"unknown"`` is used so the file is
        still uniquely named by ``run_id``.

        The log payload captures both inputs (system instruction, user
        message) and outputs (raw Gemini response, parse status, error
        message) so an entire call is reconstructable from one file —
        useful for diffing two prompt revisions on the same transcript or
        pasting back into Gemini chat to debug a malformed response.

        Failure to write the log is logged at WARN level but never raised:
        debug logging must not break extraction.

        Returns:
            ``Path`` to the written log file on success; ``None`` if writing
            failed (so the caller can surface the gap without crashing).
        """
        run_id = payload.get("run_id", "unknown")
        youtube_video_id = payload.get("youtube_video_id") or "unknown"
        ts = payload.get("started_at") or datetime.now(timezone.utc).isoformat()
        safe_ts = ts.replace(":", "-")
        filename = f"{safe_ts}_yt{youtube_video_id}_r{run_id}.json"
        path = self.EXTRACTION_LOG_DIR / filename
        try:
            self.EXTRACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            return path
        except Exception as e:
            logger.warning(
                f"{self.FULL_NAME}: failed to write extraction log {path}: {e}"
            )
            return None
