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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agent_kit.utility_classes import run_logging
from app.agent_kit.utility_classes.llm_text_query import LLMTextQuery, ModelEnum
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

    # Per-extractor model selection. ``None`` falls back to the provider's default
    # in :data:`~app.data.enum_classes.DEFAULT_MODEL_FOR_PROVIDER`. Subclasses
    # override this to pin a specific Gemini model (e.g. ``GeminiModel.GEMINI_3_PRO_PREVIEW``
    # for long-context extraction work). Callers may also override at construction
    # time once we wire that into the extractor classes themselves.
    MODEL: ClassVar[Optional[ModelEnum]] = None

    def _resolve_model(self, model_override: Optional[ModelEnum] = None) -> Optional[ModelEnum]:
        """Per-call model: ``model_override`` when set, else the class default."""
        return model_override if model_override is not None else self.MODEL

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

    # Default TTL (seconds) for transcripts uploaded via
    # :meth:`_create_extraction_cache`. 900s comfortably covers a multi-pass
    # extraction. If real-world runs ever brush against this, the follow-up
    # is to expose a ``gemini_extend_cache`` call between passes.
    EXTRACTION_CACHE_TTL_SECONDS: ClassVar[int] = 900

    def _call_llm_and_parse(
        self,
        system_instruction: str,
        user_message: str,
        *,
        youtube_video_id: Optional[str] = None,
        run_id: Optional[str] = None,
        pass_label: str = "main",
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

        Sibling of :meth:`_call_cached_llm_and_parse`. This is the
        **non-cached** path — single-shot generate, no transcript upload.
        Gemma's four-pass extraction does NOT use this method; it uses the
        cached path. See docs/extraction-pipeline-refactor-notes.md.
        """
        run_id = run_id or str(uuid.uuid4())
        llm = LLMTextQuery(provider=self.PROVIDER, model=self.MODEL)
        meta = llm.llm_metadata()
        started_at = datetime.now(timezone.utc).isoformat()

        result_success = False
        result_message = ""
        result_data: Optional[Dict[str, Any]] = None
        parse_status = "success"
        error: Optional[str] = None
        raw_response: Any = None
        raw_text: Optional[str] = None

        perf_start = time.perf_counter()
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

        elapsed_seconds = round(time.perf_counter() - perf_start, 3)
        token_usage = dict(llm.usage_total)
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
                "elapsed_seconds": elapsed_seconds,
                "token_usage": token_usage,
                "pass_label": pass_label,
                "system_instruction": system_instruction,
                "user_message": user_message,
                "raw_response": log_raw,
                "parse_status": parse_status,
                "error": error,
            }
        )
        self._record_pass_metric(
            youtube_video_id=youtube_video_id,
            run_id=run_id,
            pass_label=pass_label,
            model=meta.get("model"),
            elapsed_seconds=elapsed_seconds,
            token_usage=token_usage,
            started_at=started_at,
            completed_at=completed_at,
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
            "elapsed_seconds": elapsed_seconds,
            "token_usage": token_usage,
        }

    def _write_extraction_log(self, payload: Dict[str, Any]) -> Optional[Path]:
        """
        Write a per-call JSON debug log into the video's folder.

        Delegates to :func:`run_logging.write_call_log`, which lands the file
        at ``logs/<youtube_id>/<utc_iso_ts>_extract_<pass_label>_r<run_id>.json``
        (``:`` in the timestamp replaced with ``-`` for cross-platform safety).
        When ``youtube_video_id`` is missing the folder/filename use
        ``"unknown"``; when ``pass_label`` is missing ``"main"`` is used so
        single-pass extractor calls have stable filenames.

        The log payload captures both inputs (system instruction, user
        message) and outputs (raw Gemini response, parse status, error
        message, elapsed time, token usage) so an entire call is
        reconstructable from one file.

        Failure to write the log is logged at WARN level but never raised:
        debug logging must not break extraction.

        Returns:
            ``Path`` to the written log file on success; ``None`` if writing
            failed (so the caller can surface the gap without crashing).
        """
        run_id = payload.get("run_id", "unknown")
        youtube_video_id = payload.get("youtube_video_id") or "unknown"
        pass_label = payload.get("pass_label") or "main"
        started_at = payload.get("started_at")
        return run_logging.write_call_log(
            youtube_video_id,
            "extract",
            f"{pass_label}_r{run_id}",
            started_at,
            payload,
        )

    def _record_pass_metric(
        self,
        *,
        youtube_video_id: Optional[str],
        run_id: str,
        pass_label: str,
        model: Optional[str],
        elapsed_seconds: float,
        token_usage: Dict[str, int],
        started_at: str,
        completed_at: str,
    ) -> None:
        """Append this pass's timing + tokens into the video's metrics.json.

        Lands under the ``extraction`` stage's ``passes`` list; the stage's
        full wall-clock duration is set separately by the caller via
        :func:`run_logging.set_stage_duration`.
        """
        run_logging.record_extraction_pass(
            youtube_video_id,
            {
                "pass": pass_label,
                "model": model,
                "duration": run_logging.format_duration(elapsed_seconds),
                "elapsed_seconds": elapsed_seconds,
                "tokens": token_usage,
                "started_at": started_at,
                "completed_at": completed_at,
            },
            run_id=run_id,
            model=model,
        )

    # ------------------------------------------------------------------
    # Multi-pass cached-content helpers (Gemini-only)
    # ------------------------------------------------------------------

    def _create_extraction_cache(
        self,
        transcript: str,
        *,
        run_id: str,
        youtube_video_id: Optional[str] = None,
        display_name: Optional[str] = None,
        model: Optional[ModelEnum] = None,
        system_instruction: Optional[str] = None,
        cache_pass_label: str = "cache_create",
    ) -> Optional[str]:
        """Upload ``transcript`` as a Gemini ``CachedContent`` and return its name.

        Gemma runs one cache per pass with that pass's ``system_instruction``
        baked in at create time (Gemini forbids system_instruction on generate
        when ``cached_content`` is set). ``run_id`` ties per-pass log files
        together.

        Returns:
            ``cache_name`` string on success; ``None`` when the cache create
            failed. Also writes a ``p{cache_pass_label}`` log file so failures
            are traceable from disk without re-running the extraction.

        Call chain — cached Gemini extraction (one block runs per pass, three passes per extraction):

          GemmaNye.extract
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee
              → _pass_with_cached_transcript
                ├─ BaseExtractor._create_extraction_cache
                │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
                ├─ BaseExtractor._call_cached_llm_and_parse
                │    └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
                └─ BaseExtractor._delete_extraction_cache
                     └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: BaseExtractor._create_extraction_cache — uploads transcript + system prompt to Gemini cache; first hop of each pass.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        effective_model = self._resolve_model(model)
        llm = LLMTextQuery(provider=self.PROVIDER, model=effective_model)
        meta = llm.llm_metadata()
        started_at = datetime.now(timezone.utc).isoformat()
        result = llm.gemini_create_cache(
            transcript,
            ttl_seconds=self.EXTRACTION_CACHE_TTL_SECONDS,
            display_name=display_name,
            system_instruction=system_instruction,
        )
        completed_at = datetime.now(timezone.utc).isoformat()

        success = isinstance(result, str)
        cache_name: Optional[str] = result if success else None
        error: Optional[str] = None
        if not success:
            try:
                body = result.body.decode("utf-8")  # type: ignore[union-attr]
                error = json.loads(body).get("error", body) or "cache create failed"
            except Exception:
                error = "cache create failed"
            logger.warning(
                f"{self.FULL_NAME}: cache create failed yt={youtube_video_id or 'unknown'} "
                f"run_id={run_id}: {error}"
            )

        self._write_extraction_log(
            {
                "run_id": run_id,
                "youtube_video_id": youtube_video_id,
                "extractor_name": self.FULL_NAME,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "started_at": started_at,
                "completed_at": completed_at,
                "pass_label": cache_pass_label,
                "ttl_seconds": self.EXTRACTION_CACHE_TTL_SECONDS,
                "transcript_chars": len(transcript or ""),
                "display_name": display_name,
                "cache_name": cache_name,
                "parse_status": "success" if success else "api_error",
                "error": error,
            }
        )
        return cache_name

    def _delete_extraction_cache(
        self, cache_name: Optional[str], *, model: Optional[ModelEnum] = None
    ) -> None:
        """Best-effort cache cleanup; never raises.

        Safe to call from a ``finally`` block. Accepts ``None`` so callers
        do not have to gate the call on cache-create success.

        Call chain — cached Gemini extraction (one block runs per pass, three passes per extraction):

          GemmaNye.extract
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee
              → _pass_with_cached_transcript
                ├─ BaseExtractor._create_extraction_cache
                │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
                ├─ BaseExtractor._call_cached_llm_and_parse
                │    └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
                └─ BaseExtractor._delete_extraction_cache
                     └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: BaseExtractor._delete_extraction_cache — cleanup hop of each pass; runs in a finally block.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        if not cache_name:
            return
        try:
            LLMTextQuery(
                provider=self.PROVIDER, model=self._resolve_model(model)
            ).gemini_delete_cache(cache_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"{self.FULL_NAME}: cache delete swallowed exception cache={cache_name}: {e}"
            )

    def _call_cached_llm_and_parse(
        self,
        cache_name: str,
        *,
        run_id: str,
        pass_label: str,
        system_instruction: Optional[str] = None,
        user_message: str,
        response_schema: Optional[type[BaseModel]] = None,
        youtube_video_id: Optional[str] = None,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """Cached-content equivalent of :meth:`_call_llm_and_parse`.

        Accepts an externally-generated ``run_id`` so every pass in one
        logical extraction shares the same identifier across log files and
        downstream anchor rows. ``pass_label`` distinguishes per-pass logs
        (e.g. ``"extract"``, ``"fact_check"``, ``"bullets"``).

        Pass ``system_instruction=None`` when the system prompt was already
        set on the cache at create time (Gemma's per-pass cache pattern).

        When ``response_schema`` is given, Gemini constrains its output to
        the Pydantic shape and this method returns the parsed ``dict`` in
        the envelope's ``data`` field. When omitted, the raw text is parsed
        as JSON the same way :meth:`_call_llm_and_parse` does.

        Call chain — cached Gemini extraction (one block runs per pass, three passes per extraction):

          GemmaNye.extract
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee
              → _pass_with_cached_transcript
                ├─ BaseExtractor._create_extraction_cache
                │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
                ├─ BaseExtractor._call_cached_llm_and_parse
                │    └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
                └─ BaseExtractor._delete_extraction_cache
                     └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: BaseExtractor._call_cached_llm_and_parse — middle hop of each pass; sends the generate request against the cache and parses the response.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        effective_model = self._resolve_model(model)
        llm = LLMTextQuery(provider=self.PROVIDER, model=effective_model)
        meta = llm.llm_metadata()
        started_at = datetime.now(timezone.utc).isoformat()

        result_success = False
        result_message = ""
        result_data: Optional[Dict[str, Any]] = None
        parse_status = "success"
        error: Optional[str] = None
        raw_response: Any = None
        raw_text: Optional[str] = None

        perf_start = time.perf_counter()
        try:
            raw = llm.gemini_generate_with_cache(
                cache_name,
                system_instruction=system_instruction,
                user_message=user_message,
                response_schema=response_schema,
            )
        except Exception as e:
            logger.exception(f"{self.FULL_NAME}: cached LLM call raised pass={pass_label}")
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
                    f"{self.FULL_NAME}: cached LLM returned error envelope pass={pass_label}: {err}"
                )
                parse_status = "api_error"
                error = f"LLM request failed: {err}"
                result_message = error
            elif isinstance(raw, dict):
                # response_schema path: Gemini returned a parsed dict directly.
                raw_response = raw
                result_data = raw
                result_success = True
                result_message = "Extraction complete"
            else:
                raw_text = (raw or "").strip()
                text = raw_text
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```\s*$", "", text)
                try:
                    data = json.loads(text) if text else None
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"{self.FULL_NAME}: invalid JSON from cached LLM pass={pass_label}: {e}"
                    )
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
                        result_success = True
                        result_message = "Extraction complete"
                        result_data = data

        elapsed_seconds = round(time.perf_counter() - perf_start, 3)
        token_usage = dict(llm.usage_total)
        completed_at = datetime.now(timezone.utc).isoformat()
        log_raw = raw_response if raw_response is not None else raw_text
        self._write_extraction_log(
            {
                "run_id": run_id,
                "youtube_video_id": youtube_video_id,
                "extractor_name": self.FULL_NAME,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "started_at": started_at,
                "completed_at": completed_at,
                "elapsed_seconds": elapsed_seconds,
                "token_usage": token_usage,
                "pass_label": pass_label,
                "cache_name": cache_name,
                "response_schema": response_schema.__name__ if response_schema else None,
                "system_instruction": system_instruction,
                "user_message": user_message,
                "raw_response": log_raw,
                "parse_status": parse_status,
                "error": error,
            }
        )
        self._record_pass_metric(
            youtube_video_id=youtube_video_id,
            run_id=run_id,
            pass_label=pass_label,
            model=meta.get("model"),
            elapsed_seconds=elapsed_seconds,
            token_usage=token_usage,
            started_at=started_at,
            completed_at=completed_at,
        )

        return {
            **meta,
            "run_id": run_id,
            "success": result_success,
            "message": result_message,
            "data": result_data,
            "elapsed_seconds": elapsed_seconds,
            "token_usage": token_usage,
        }
