"""
Gemma Nye — Fall River meeting-data extractor (four-pass Gemini pipeline).

One :meth:`GemmaNye.extract` call runs four sequential Gemini reading
passes against the transcript. The transcript is uploaded to a single
:class:`CachedContent` once per extraction (``cache.create`` →
four × ``generate`` → ``cache.delete``) and reused by all four passes.
Gemini forbids ``system_instruction`` on ``generate`` when
``cached_content`` is set, so each pass's (different) system prompt is
folded into its user turn instead of baked into the cache — which is
exactly what lets the four passes share one cache:

1. ``extract`` — draft factual anchors (Pydantic-constrained shape).
2. ``fact_check`` — re-emit the corrected full list of anchors, plus a
   unified ``fact_check_audit`` log of every draft removed / corrected /
   added. Per-anchor ``fact_check_note`` is an uncertainty caveat the
   model populates only when it wants to flag self-doubt.
3. ``bullets`` — 5-8 executive bullets plus committee classification.
4. ``spell_check`` — re-emit the pass-2 anchors AND the pass-3 bullets
   with canonical Fall River spellings applied (officials, boards,
   streets — list inlined into the pass-4 system instructions). Parallel
   ``spelling_corrections`` audit log records every term replaced.
   Replaced EditorAgent's post-hoc article spell-check; spelling now
   happens at the anchor layer, before journalists ever see the data.

The four passes are independent on the LLM side: the shared cache carries
only the transcript, and no conversation history flows between calls.
Cross-pass data dependencies flow only through the user message: pass 2
sees pass 1's draft anchors; pass 4 sees both pass 2's corrected anchors
and pass 3's bullets. None of that traffic relies on Gemini remembering
anything.

After pass 4, we stitch in ``timestamp_seconds`` (parsed directly from the
model's ``timestamp_string``) and ``text_to_embed`` (a one-line formatted
summary suitable for downstream vector indexing) locally — these are
deterministic transformations that don't need an LLM. The extractor chooses
the timestamp at the start of each topic; we do not re-align against the
transcript. When a fact-check ``fact_check_note`` is present, it is appended
into ``text_to_embed`` so the uncertainty caveat rides along into RAG.

Persistence stays with the caller. :meth:`extract` returns the envelope;
caller hands it to :class:`~app.data.anchor_manager.AnchorManager`, which
writes anchors + bullets to ``anchors``, fact-check audit rows to
``fact_check_removals``, and spelling-correction audit rows to
``spelling_corrections``.
"""

import json
import logging
import re
import uuid
from typing import Any, ClassVar, Dict, List, Optional

from app.agent_kit.agents.extractors.base_extractor import BaseExtractor
from app.agent_kit.agents.extractors.schemas import (
    BulletsAndCommittee,
    ExtractEnvelope,
    FactCheckEnvelope,
    SpellCheckEnvelope,
)
from app.agent_kit.utility_classes.llm_text_query import ModelEnum
from app.agent_kit.utility_classes.prompt_utilities import format_bracket_timestamp
from app.data.enum_classes import (
    Committee,
    GeminiModel,
    committee_list_for_prompt,
)

logger = logging.getLogger(__name__)


class GemmaNye(BaseExtractor):
    """
    Gemma Nye — Fall River meeting-data extractor.

    Operational content lives in markdown, not Python. Four system/user
    prompt pairs (one per LLM-reading pass):

    - ``context_files/system_instructions/gemma_nye_extract_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_extract_user_prompt.md``
    - ``context_files/system_instructions/gemma_nye_fact_check_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_fact_check_user_prompt.md``
    - ``context_files/system_instructions/gemma_nye_bullets_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_bullets_user_prompt.md``
    - ``context_files/system_instructions/gemma_nye_spell_check_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_spell_check_user_prompt.md``

    Plus the existing bio / description pair.

    The class itself owns only identity traits, the chosen Gemini model,
    and the four-pass orchestration in :meth:`extract`.

    Four-pass orchestration (sequential, short-circuit on failure):

      1. ``_pass_extract``               — draft factual anchors from the transcript.
      2. ``_pass_fact_check``            — re-emit corrected anchors + fact-check audit log.
                                           Consumes pass 1's ``factual_anchor_items``.
      3. ``_pass_bullets_and_committee`` — executive bullets + committee classification.
                                           Independent of passes 1 and 2; reads only
                                           the transcript.
      4. ``_pass_spell_check``           — re-emit pass-2 anchors AND pass-3 bullets
                                           with canonical Fall River spellings applied
                                           + spelling-corrections audit log. Consumes
                                           pass 2's ``factual_anchor_items`` and
                                           pass 3's ``executive_summary_bullets`` —
                                           the only place those two streams are joined.

    The transcript is cached once per extraction and reused by all four
    passes (``cache.create`` → four × ``generate`` → ``cache.delete``).
    Because Gemini forbids ``system_instruction`` on ``generate`` when
    ``cached_content`` is set, each pass's (different) system prompt is
    folded into its user turn rather than baked into the cache. Inter-pass
    communication happens through the user message only
    (``draft["data"]["factual_anchor_items"]`` for pass 2; pass-2 anchors +
    pass-3 bullets for pass 4) — never through conversation history.

    On any pass failure, :meth:`extract` returns that pass's failure
    envelope immediately — no downstream pass runs, no partial result is
    stitched. See :meth:`extract` for the full envelope shape and
    ``docs/extraction-pipeline-refactor-notes.md`` for the broader call chain.
    """

    FIRST_NAME = "Gemma"
    LAST_NAME = "Nye"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    # SLANT and STYLE describe Gemma's methodology, not political angle / prose voice.
    SLANT = "neutral"
    STYLE = "structured"

    # Long-context Gemini preview is the right tool for transcripts that can
    # reach hundreds of thousands of tokens. Override at instantiation time if
    # you want to compare cost/quality against a cheaper model.
    MODEL: ClassVar[Optional[ModelEnum]] = GeminiModel.GEMINI_3_PRO_PREVIEW

    # Suffix conventions: the existing BaseExtractor pair loaders read
    # ``{first}_{last}_system_instructions.md`` / ``_user_prompt.md``. The
    # four-pass design needs four separate pairs, so we load each pair by
    # passing an explicit suffix to ``_load_named_prompt`` below.
    _EXTRACT_SYSTEM_SUFFIX: ClassVar[str] = "_extract_system_instructions.md"
    _EXTRACT_USER_SUFFIX: ClassVar[str] = "_extract_user_prompt.md"
    _FACT_CHECK_SYSTEM_SUFFIX: ClassVar[str] = "_fact_check_system_instructions.md"
    _FACT_CHECK_USER_SUFFIX: ClassVar[str] = "_fact_check_user_prompt.md"
    _BULLETS_SYSTEM_SUFFIX: ClassVar[str] = "_bullets_system_instructions.md"
    _BULLETS_USER_SUFFIX: ClassVar[str] = "_bullets_user_prompt.md"
    _SPELL_CHECK_SYSTEM_SUFFIX: ClassVar[str] = "_spell_check_system_instructions.md"
    _SPELL_CHECK_USER_SUFFIX: ClassVar[str] = "_spell_check_user_prompt.md"

    @staticmethod
    def _video_duration_label(
        video_duration_formatted: Optional[str],
        video_duration_seconds: Optional[int],
    ) -> str:
        """Human-readable duration for extract/fact-check user prompts."""
        if video_duration_formatted and str(video_duration_formatted).strip():
            return str(video_duration_formatted).strip()
        if video_duration_seconds is not None and int(video_duration_seconds) > 0:
            total = int(video_duration_seconds)
            hours, rem = divmod(total, 3600)
            minutes, secs = divmod(rem, 60)
            if hours:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            return f"{minutes}:{secs:02d}"
        return "unknown"

    def extract(
        self,
        transcript: str,
        youtube_video_id: str,
        meeting_date: str,
        primary_committee: Optional[str] = None,
        model: Optional[ModelEnum] = None,
        video_duration_formatted: Optional[str] = None,
        video_duration_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured factual anchors from a Fall River meeting transcript.

        Args:
            transcript: Full transcript text.
            youtube_video_id: 11-character YouTube id. Acts as the meeting's
                stable, globally unique identifier and is the FK that
                ``anchors`` rows carry back to ``transcripts``.
            meeting_date: ISO 8601 date (YYYY-MM-DD) of the meeting.
            video_duration_formatted: Wall-clock duration from the transcript
                row (e.g. ``"3:46:49"``), injected into extract/fact-check
                user prompts as ``VIDEO_DURATION``.
            video_duration_seconds: Fallback when formatted duration is missing.
            primary_committee: Ignored. Kept in the signature for
                backward-compat with the previous single-pass call shape;
                Gemma now classifies the committee herself in pass 3.

        Returns:
            ``{"provider", "model", "run_id", "success", "message", "data"}``
            envelope. ``run_id`` is shared across all four pass log files
            and is the FK callers stamp onto ``anchors`` rows when
            persisting. ``data`` on success contains:

            - ``factual_anchor_items`` — spelling-clean anchors from the
              spell-check pass (which took the fact-check pass's corrected
              anchors as input), each augmented locally with
              ``timestamp_seconds`` and ``text_to_embed``. Each anchor may
              carry a ``fact_check_note`` uncertainty caveat from the
              fact-check pass (empty string when the model was confident);
              when non-empty the caveat is appended into ``text_to_embed``
              so RAG queries see it. Pass 4 round-trips ``fact_check_note``
              verbatim — it only edits spellings, not facts.
            - ``executive_summary_bullets`` — spelling-clean list of summary
              bullets from the spell-check pass (which took the bullets
              pass's output as input).
            - ``primary_committee`` — committee enum string from the
              bullets pass.
            - ``fact_check_audit`` — unified audit log of every draft the
              fact-check pass removed, corrected, or added. Each entry
              carries ``kind`` (``'removed' | 'corrected' | 'added'``),
              originals (verbatim from the draft for removed/corrected;
              null for added), ``corrected_anchor_text`` (verbatim copy of
              the matching ``factual_anchor_items`` entry for
              corrected/added; null for removed), and ``audit_note``
              (empty when the model was confident in the decision). Empty
              list is the common case. Callers should pass this through to
              :class:`~app.data.anchor_manager.AnchorManager.insert_from_envelope`
              so the audit rows land in ``fact_check_removals``.
            - ``spelling_corrections`` — parallel audit log of every term
              the spell-check pass replaced. Each entry carries
              ``target_kind`` (``'factual_anchor' | 'executive_summary'``),
              ``corrected_anchor_text`` (verbatim copy of the post-pass-4
              anchor or bullet string — used as the join key to
              ``anchors.id``), ``original_term``, ``corrected_term``, and
              ``audit_note`` (empty when the model was confident). Empty
              list when no misspellings were found. Persistence lands the
              rows in ``spelling_corrections``.

            On any pass failure, ``success`` is ``False`` and ``data`` is
            ``None``; per-pass debug logs under ``logs/extractions/`` reveal
            which pass failed. The cache is always deleted on the way out.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye.extract — orchestrator. Runs the four passes in sequence and stitches results.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        if primary_committee is not None:
            logger.debug(
                f"{self.FULL_NAME}: ignoring caller-supplied primary_committee=%r "
                "(Gemma classifies fresh in pass 3)",
                primary_committee,
            )

        run_id = str(uuid.uuid4())
        video_duration = self._video_duration_label(
            video_duration_formatted, video_duration_seconds
        )
        logger.info(
            f"{self.FULL_NAME}: extraction start yt={youtube_video_id} "
            f"run_id={run_id} transcript_chars={len(transcript or '')} "
            f"video_duration={video_duration}"
        )

        # ─────────────────────────────────────────────────────────────────
        # Four-pass orchestration. Sequential, short-circuit on failure.
        #
        #   pass 1: _pass_extract               → draft anchors
        #   pass 2: _pass_fact_check            → corrected anchors + fact-check audit
        #                                         (consumes draft["data"]["factual_anchor_items"])
        #   pass 3: _pass_bullets_and_committee → bullets + committee
        #                                         (independent; reads only the transcript)
        #   pass 4: _pass_spell_check           → spelling-clean anchors + bullets
        #                                         + spelling-corrections audit
        #                                         (consumes pass-2 anchors AND pass-3 bullets —
        #                                         the only place those two streams are joined)
        #
        # The transcript is uploaded to a single Gemini cache once here and
        # reused by all four passes. Each pass folds its own (different)
        # system prompt into the user turn at generate time instead of
        # baking it into the cache, so we no longer create and delete a
        # cache per pass. The cache is deleted exactly once in the finally
        # below, on every exit path (success or any pass failure).
        #
        # If any pass fails we return its failure envelope immediately;
        # no later pass runs and no partial result is stitched below.
        # ─────────────────────────────────────────────────────────────────
        cache_name = self._create_extraction_cache(
            transcript,
            run_id=run_id,
            youtube_video_id=youtube_video_id,
            display_name=f"gemma:{youtube_video_id}:shared",
            model=model,
            system_instruction=None,
            cache_pass_label="cache",
        )
        if not cache_name:
            return self._failure_envelope(
                run_id,
                "Gemini cache create failed; see pcache log for details.",
                model=model,
            )

        try:
            draft = self._pass_extract(
                cache_name,
                run_id,
                youtube_video_id,
                meeting_date,
                video_duration=video_duration,
                model=model,
            )
            if not draft["success"]:
                return draft

            corrected = self._pass_fact_check(
                cache_name,
                run_id,
                youtube_video_id,
                meeting_date,
                draft["data"]["factual_anchor_items"],
                video_duration=video_duration,
                model=model,
            )
            if not corrected["success"]:
                return corrected

            bullets_committee = self._pass_bullets_and_committee(
                cache_name, run_id, youtube_video_id, meeting_date, model=model
            )
            if not bullets_committee["success"]:
                return bullets_committee

            spell_checked = self._pass_spell_check(
                cache_name,
                run_id,
                youtube_video_id,
                meeting_date,
                corrected["data"]["factual_anchor_items"],
                bullets_committee["data"]["executive_summary_bullets"],
                model=model,
            )
            if not spell_checked["success"]:
                return spell_checked

            committee_value = bullets_committee["data"]["primary_committee"]
            if isinstance(committee_value, Committee):
                committee_str = committee_value.value
            else:
                committee_str = str(committee_value)

            # Stitch on pass-4 anchors so the locally-computed `text_to_embed`
            # rides the spelling-clean wording into the vector store, not the
            # pre-spell-check version.
            stitched_anchors = [
                self._stitch_anchor(a, meeting_date, committee_str)
                for a in spell_checked["data"]["factual_anchor_items"]
            ]

            fact_check_audit = corrected["data"].get("fact_check_audit") or []
            spelling_corrections = (
                spell_checked["data"].get("spelling_corrections") or []
            )
            envelope = {
                **draft,
                "run_id": run_id,
                "success": True,
                "message": "Extraction complete",
                "data": {
                    "factual_anchor_items": stitched_anchors,
                    # Bullets sourced from pass 4 (spelling-clean), not pass 3.
                    "executive_summary_bullets": spell_checked["data"][
                        "executive_summary_bullets"
                    ],
                    "primary_committee": committee_str,
                    "fact_check_audit": fact_check_audit,
                    "spelling_corrections": spelling_corrections,
                },
            }
            logger.info(
                f"{self.FULL_NAME}: extraction done yt={youtube_video_id} run_id={run_id} "
                f"anchors={len(stitched_anchors)} "
                f"bullets={len(envelope['data']['executive_summary_bullets'])} "
                f"fact_check_audit={len(fact_check_audit)} "
                f"spelling_corrections={len(spelling_corrections)} "
                f"committee={committee_str!r}"
            )
            return envelope
        finally:
            self._delete_extraction_cache(cache_name, model=model)

    # ------------------------------------------------------------------
    # Per-pass helpers
    # ------------------------------------------------------------------

    def _run_pass_against_cache(
        self,
        cache_name: str,
        *,
        run_id: str,
        pass_label: str,
        youtube_video_id: str,
        system_instruction: str,
        user_message: str,
        response_schema: type,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """One Gemma pass: generate against the shared transcript cache.

        Shared body of the four per-pass methods (``_pass_extract``,
        ``_pass_fact_check``, ``_pass_bullets_and_committee``,
        ``_pass_spell_check``). The transcript cache is created and deleted
        once by :meth:`extract`; this helper does not own the cache
        lifecycle. Because Gemini forbids ``system_instruction`` on generate
        when ``cached_content`` is set, each pass's (different) system prompt
        is folded into the user turn instead of baked into the cache (see
        :meth:`LLMTextQuery._cached_turn_contents`), which is what lets all
        four passes share one cache.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye._run_pass_against_cache — issues one generate against the shared cache, folding this pass's system prompt into the user turn.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        return self._call_cached_llm_and_parse(
            cache_name,
            run_id=run_id,
            pass_label=pass_label,
            system_instruction=system_instruction,
            user_message=user_message,
            response_schema=response_schema,
            youtube_video_id=youtube_video_id,
            model=model,
        )

    def _pass_extract(
        self,
        cache_name: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        *,
        video_duration: str = "unknown",
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """Pass 1 of 4 — draft factual anchors from the transcript.

        Loads ``gemma_nye_extract_*.md`` prompts, constrains output to
        :class:`ExtractEnvelope`, delegates the generate against the shared
        transcript cache to :meth:`_run_pass_against_cache`.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye._pass_extract — pass 1 of 4, picks extract prompts + ExtractEnvelope schema.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        return self._run_pass_against_cache(
            cache_name,
            run_id=run_id,
            pass_label="extract",
            youtube_video_id=youtube_video_id,
            system_instruction=self._load_named_prompt(
                self.SYSTEM_INSTRUCTION_SUBDIR, self._EXTRACT_SYSTEM_SUFFIX
            ),
            user_message=self._render_named_user_prompt(
                self._EXTRACT_USER_SUFFIX,
                youtube_video_id=youtube_video_id,
                meeting_date=meeting_date,
                video_duration=video_duration,
            ),
            response_schema=ExtractEnvelope,
            model=model,
        )

    def _pass_fact_check(
        self,
        cache_name: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        draft_anchors: List[Dict[str, Any]],
        *,
        video_duration: str = "unknown",
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """Pass 2 of 4 — fact-check draft anchors against the transcript.

        Loads ``gemma_nye_fact_check_*.md`` prompts, injects the draft
        anchors from pass 1 into the user prompt as ``draft_anchors_json``,
        constrains output to :class:`FactCheckEnvelope`, delegates the
        generate against the shared transcript cache to
        :meth:`_run_pass_against_cache`. The fact-check *logic* lives in the
        markdown file, not here — this method only ferries the draft into
        the user prompt.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye._pass_fact_check — pass 2 of 4, picks fact-check prompts + FactCheckEnvelope schema, injects draft anchors.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        draft_anchors_json = json.dumps(draft_anchors, ensure_ascii=False, indent=2)
        return self._run_pass_against_cache(
            cache_name,
            run_id=run_id,
            pass_label="fact_check",
            youtube_video_id=youtube_video_id,
            system_instruction=self._load_named_prompt(
                self.SYSTEM_INSTRUCTION_SUBDIR, self._FACT_CHECK_SYSTEM_SUFFIX
            ),
            user_message=self._render_named_user_prompt(
                self._FACT_CHECK_USER_SUFFIX,
                youtube_video_id=youtube_video_id,
                meeting_date=meeting_date,
                video_duration=video_duration,
                draft_anchors_json=draft_anchors_json,
            ),
            response_schema=FactCheckEnvelope,
            model=model,
        )

    def _pass_bullets_and_committee(
        self,
        cache_name: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        *,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """Pass 3 of 4 — executive bullets + committee classification.

        Loads ``gemma_nye_bullets_*.md`` prompts, injects the canonical
        committee list into the user prompt, constrains output to
        :class:`BulletsAndCommittee`, delegates the generate against the
        shared transcript cache to :meth:`_run_pass_against_cache`.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye._pass_bullets_and_committee — pass 3 of 4, picks bullets prompts + BulletsAndCommittee schema.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        return self._run_pass_against_cache(
            cache_name,
            run_id=run_id,
            pass_label="bullets",
            youtube_video_id=youtube_video_id,
            system_instruction=self._load_named_prompt(
                self.SYSTEM_INSTRUCTION_SUBDIR, self._BULLETS_SYSTEM_SUFFIX
            ),
            user_message=self._render_named_user_prompt(
                self._BULLETS_USER_SUFFIX,
                youtube_video_id=youtube_video_id,
                meeting_date=meeting_date,
                committee_list=committee_list_for_prompt(),
            ),
            response_schema=BulletsAndCommittee,
            model=model,
        )

    def _pass_spell_check(
        self,
        cache_name: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        corrected_anchors: List[Dict[str, Any]],
        bullets: List[str],
        *,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """Pass 4 of 4 — apply canonical spellings to anchors and bullets.

        Loads ``gemma_nye_spell_check_*.md`` prompts, injects pass 2's
        corrected anchors and pass 3's bullets into the user prompt as
        ``corrected_anchors_json`` and ``bullets_json``, constrains output
        to :class:`SpellCheckEnvelope`, delegates the generate against the
        shared transcript cache to :meth:`_run_pass_against_cache`. The
        canonical Fall River names list (officials, boards, streets) is
        baked into the pass-4 system instructions markdown — this method
        does not ferry any names list into Python.

        Call chain — cached Gemini extraction (cache created once in extract; one generate per pass):

          GemmaNye.extract
            ├─ BaseExtractor._create_extraction_cache (once)
            │    └─ LLMTextQuery.gemini_create_cache         → client.caches.create
            → _pass_extract / _pass_fact_check / _pass_bullets_and_committee / _pass_spell_check
              → _run_pass_against_cache
                └─ BaseExtractor._call_cached_llm_and_parse
                     └─ LLMTextQuery.gemini_generate_with_cache  → client.models.generate_content  ★
            └─ BaseExtractor._delete_extraction_cache (once, in finally)
                 └─ LLMTextQuery.gemini_delete_cache         → client.caches.delete

        ★ = the actual Gemini round-trip (the LLM "extraction request" you're tracing).
        YOU ARE HERE: GemmaNye._pass_spell_check — pass 4 of 4, picks spell-check prompts + SpellCheckEnvelope schema, injects pass-2 anchors + pass-3 bullets.
        See docs/extraction-pipeline-refactor-notes.md for layering rationale and refactor targets.
        """
        corrected_anchors_json = json.dumps(
            corrected_anchors, ensure_ascii=False, indent=2
        )
        bullets_json = json.dumps(bullets, ensure_ascii=False, indent=2)
        return self._run_pass_against_cache(
            cache_name,
            run_id=run_id,
            pass_label="spell_check",
            youtube_video_id=youtube_video_id,
            system_instruction=self._load_named_prompt(
                self.SYSTEM_INSTRUCTION_SUBDIR, self._SPELL_CHECK_SYSTEM_SUFFIX
            ),
            user_message=self._render_named_user_prompt(
                self._SPELL_CHECK_USER_SUFFIX,
                youtube_video_id=youtube_video_id,
                meeting_date=meeting_date,
                corrected_anchors_json=corrected_anchors_json,
                bullets_json=bullets_json,
            ),
            response_schema=SpellCheckEnvelope,
            model=model,
        )

    def _render_named_user_prompt(self, suffix: str, **kwargs: Any) -> str:
        """Load a user-prompt template by suffix and apply ``{key}`` substitution.

        Mirrors :meth:`BaseExtractor._render_user_prompt` but lets us pick
        which suffix to load so the four-pass design can use three different
        user-prompt files.
        """
        template = self._load_named_prompt(self.USER_PROMPT_SUBDIR, suffix)
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            rendered_value = "null" if value is None else str(value)
            template = template.replace(placeholder, rendered_value)
        return template

    # ------------------------------------------------------------------
    # Local stitching (no LLM involved)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_timestamp_to_seconds(ts: Optional[str]) -> Optional[int]:
        """Parse a transcript timestamp marker into whole seconds.

        Accepts decimal floats from YouTube caption JSON (truncated toward
        zero), plain integers, ``Ns`` suffixes, and ``MM:SS`` / ``HH:MM:SS``.
        Returns ``None`` when the input is empty or unparseable.
        """
        if not ts or not isinstance(ts, str):
            return None
        raw = ts.strip()
        if not raw:
            return None
        if re.fullmatch(r"\d+\.\d+", raw):
            try:
                return int(float(raw))
            except ValueError:
                return None
        if raw.isdigit():
            return int(raw)
        if raw.endswith("s") and raw[:-1].isdigit():
            return int(raw[:-1])
        parts = raw.split(":")
        if not all(re.fullmatch(r"\d+", p) for p in parts):
            return None
        try:
            if len(parts) == 3:
                h, m, s = (int(p) for p in parts)
                return h * 3600 + m * 60 + s
            if len(parts) == 2:
                m, s = (int(p) for p in parts)
                return m * 60 + s
        except ValueError:
            return None
        return None

    @staticmethod
    def format_timestamp_colon(seconds: int) -> str:
        """Zero-padded ``MM:SS`` or ``HH:MM:SS`` for stored ``timestamp_string``."""
        total = max(0, int(seconds))
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def format_timestamp_bracket(seconds: int) -> str:
        """Bracketed video jump label, e.g. ``[00:12]`` or ``[01:08:44]``."""
        return format_bracket_timestamp(seconds)

    @staticmethod
    def _build_text_to_embed(
        anchor: Dict[str, Any], meeting_date: str, committee: str
    ) -> str:
        """Format a single anchor as one line suitable for vector embedding.

        Base pattern:
            ``Date: {date} | Committee: {committee} | Topic: {headline} | Fact: {text}``

        When the fact-check pass populated ``fact_check_note`` on this anchor
        (i.e. the model flagged self-doubt about the anchor's content), the
        caveat is appended as ``| Caveat: {note}`` so RAG queries see the
        uncertainty alongside the fact. Confident anchors (empty/missing
        note) get the base pattern unchanged.
        """
        base = (
            f"Date: {meeting_date} | "
            f"Committee: {committee} | "
            f"Topic: {anchor.get('anchor_headline', '')} | "
            f"Fact: {anchor.get('anchor_text', '')}"
        )
        note = (anchor.get("fact_check_note") or "").strip()
        return f"{base} | Caveat: {note}" if note else base

    def _stitch_anchor(
        self,
        raw: Dict[str, Any],
        meeting_date: str,
        committee: str,
    ) -> Dict[str, Any]:
        """Combine raw LLM-emitted anchor with locally-computed fields.

        ``timestamp_seconds`` is parsed directly from the model's
        ``timestamp_string``; the extractor is responsible for choosing the
        marker at the start of the topic. No transcript re-alignment happens
        here.
        """
        ts_seconds = self.parse_timestamp_to_seconds(raw.get("timestamp_string"))
        normalized_ts = (
            self.format_timestamp_colon(ts_seconds)
            if ts_seconds is not None
            else raw.get("timestamp_string")
        )
        return {
            **raw,
            "timestamp_string": normalized_ts,
            "timestamp_seconds": ts_seconds,
            "text_to_embed": self._build_text_to_embed(raw, meeting_date, committee),
        }

    def _failure_envelope(
        self, run_id: str, message: str, *, model: Optional[ModelEnum] = None
    ) -> Dict[str, Any]:
        """Return a uniform failure-shape envelope for early-exit paths."""
        effective = self._resolve_model(model)
        return {
            "provider": self.PROVIDER.value,
            "model": (effective.value if effective is not None else None),
            "run_id": run_id,
            "success": False,
            "message": message,
            "data": None,
        }
