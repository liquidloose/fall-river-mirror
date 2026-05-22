"""
Gemma Nye — Fall River meeting-data extractor (four-pass Gemini pipeline).

One :meth:`GemmaNye.extract` call runs four sequential Gemini operations
against one shared :class:`CachedContent` upload of the transcript:

1. ``cache_create`` — upload the transcript once with a 900s TTL.
2. ``extract`` — draft factual anchors (Pydantic-constrained shape).
3. ``fact_check`` — re-emit the corrected full list of anchors.
4. ``bullets`` — 5-8 executive bullets plus committee classification.

The three LLM-reading passes are independent: only the cached transcript
is shared. Each pass gets its own system instruction, its own user message,
and its own ``response_schema``. We deliberately do not pass conversation
history between passes — the fact-check pass sees the draft anchors only
because we inject them into its user message.

After pass 4, we stitch in ``timestamp_seconds`` (parsed from each anchor's
timestamp string) and ``text_to_embed`` (a one-line formatted summary
suitable for downstream vector indexing) locally — these are deterministic
transformations that don't need an LLM.

Persistence stays with the caller. :meth:`extract` returns the envelope;
caller hands it to :class:`~app.data.anchor_manager.AnchorManager`.
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
)
from app.agent_kit.utility_classes.llm_text_query import ModelEnum
from app.data.enum_classes import (
    Committee,
    GeminiModel,
    committee_list_for_prompt,
)

logger = logging.getLogger(__name__)


class GemmaNye(BaseExtractor):
    """
    Gemma Nye — Fall River meeting-data extractor.

    Operational content lives in markdown, not Python. Three system/user
    prompt pairs (one per LLM-reading pass):

    - ``context_files/system_instructions/gemma_nye_extract_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_extract_user_prompt.md``
    - ``context_files/system_instructions/gemma_nye_fact_check_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_fact_check_user_prompt.md``
    - ``context_files/system_instructions/gemma_nye_bullets_system_instructions.md``
    - ``context_files/user_prompts/gemma_nye_bullets_user_prompt.md``

    Plus the existing bio / description pair.

    The class itself owns only identity traits, the chosen Gemini model,
    and the four-pass orchestration in :meth:`extract`.
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
    # four-pass design needs three separate pairs, so we load each pair by
    # passing an explicit suffix to ``_load_named_prompt`` below.
    _EXTRACT_SYSTEM_SUFFIX: ClassVar[str] = "_extract_system_instructions.md"
    _EXTRACT_USER_SUFFIX: ClassVar[str] = "_extract_user_prompt.md"
    _FACT_CHECK_SYSTEM_SUFFIX: ClassVar[str] = "_fact_check_system_instructions.md"
    _FACT_CHECK_USER_SUFFIX: ClassVar[str] = "_fact_check_user_prompt.md"
    _BULLETS_SYSTEM_SUFFIX: ClassVar[str] = "_bullets_system_instructions.md"
    _BULLETS_USER_SUFFIX: ClassVar[str] = "_bullets_user_prompt.md"

    def extract(
        self,
        transcript: str,
        youtube_video_id: str,
        meeting_date: str,
        primary_committee: Optional[str] = None,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured factual anchors from a Fall River meeting transcript.

        Args:
            transcript: Full transcript text.
            youtube_video_id: 11-character YouTube id. Acts as the meeting's
                stable, globally unique identifier and is the FK that
                ``anchors`` rows carry back to ``transcripts``.
            meeting_date: ISO 8601 date (YYYY-MM-DD) of the meeting.
            primary_committee: Ignored. Kept in the signature for
                backward-compat with the previous single-pass call shape;
                Gemma now classifies the committee herself in pass 4.

        Returns:
            ``{"provider", "model", "run_id", "success", "message", "data"}``
            envelope. ``run_id`` is shared across all four pass log files
            and is the FK callers stamp onto ``anchors`` rows when
            persisting. ``data`` on success contains:

            - ``factual_anchor_items`` — corrected anchors from the fact-check
              pass, each augmented locally with ``timestamp_seconds`` and
              ``text_to_embed``. Each anchor may carry a ``fact_check_note``
              field from the fact-check pass (empty string when the draft was
              re-emitted unchanged).
            - ``executive_summary_bullets`` — list of summary bullets from
              the bullets pass.
            - ``primary_committee`` — committee enum string from the
              bullets pass.
            - ``removed_drafts`` — list of draft anchors the fact-check pass
              concluded were fabricated and dropped. Each carries
              ``original_timestamp_string``, ``original_anchor_headline``,
              ``original_anchor_text``, and ``removal_reason``. Empty list
              is the common case. Callers should pass this through to
              :class:`~app.data.anchor_manager.AnchorManager.insert_from_envelope`
              so the audit rows land in ``fact_check_removals``.

            On any pass failure, ``success`` is ``False`` and ``data`` is
            ``None``; per-pass debug logs under ``logs/extractions/`` reveal
            which pass failed. The cache is always deleted on the way out.
        """
        if primary_committee is not None:
            logger.debug(
                f"{self.FULL_NAME}: ignoring caller-supplied primary_committee=%r "
                "(Gemma classifies fresh in pass 4)",
                primary_committee,
            )

        run_id = str(uuid.uuid4())
        logger.info(
            f"{self.FULL_NAME}: extraction start yt={youtube_video_id} "
            f"run_id={run_id} transcript_chars={len(transcript or '')}"
        )

        draft = self._pass_extract(
            transcript, run_id, youtube_video_id, meeting_date, model=model
        )
        if not draft["success"]:
            return draft

        corrected = self._pass_fact_check(
            transcript,
            run_id,
            youtube_video_id,
            meeting_date,
            draft["data"]["factual_anchor_items"],
            model=model,
        )
        if not corrected["success"]:
            return corrected

        bullets_committee = self._pass_bullets_and_committee(
            transcript, run_id, youtube_video_id, meeting_date, model=model
        )
        if not bullets_committee["success"]:
            return bullets_committee

        committee_value = bullets_committee["data"]["primary_committee"]
        if isinstance(committee_value, Committee):
            committee_str = committee_value.value
        else:
            committee_str = str(committee_value)

        stitched_anchors = [
            self._stitch_anchor(a, meeting_date, committee_str)
            for a in corrected["data"]["factual_anchor_items"]
        ]

        removed_drafts = corrected["data"].get("removed_drafts") or []
        envelope = {
            **draft,
            "run_id": run_id,
            "success": True,
            "message": "Extraction complete",
            "data": {
                "factual_anchor_items": stitched_anchors,
                "executive_summary_bullets": bullets_committee["data"][
                    "executive_summary_bullets"
                ],
                "primary_committee": committee_str,
                "removed_drafts": removed_drafts,
            },
        }
        logger.info(
            f"{self.FULL_NAME}: extraction done yt={youtube_video_id} run_id={run_id} "
            f"anchors={len(stitched_anchors)} "
            f"bullets={len(envelope['data']['executive_summary_bullets'])} "
            f"removed_drafts={len(removed_drafts)} "
            f"committee={committee_str!r}"
        )
        return envelope

    # ------------------------------------------------------------------
    # Per-pass helpers
    # ------------------------------------------------------------------

    def _pass_with_cached_transcript(
        self,
        transcript: str,
        *,
        run_id: str,
        pass_label: str,
        youtube_video_id: str,
        system_instruction: str,
        user_message: str,
        response_schema: type,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        """One Gemma pass: cache transcript + system prompt, then generate."""
        cache_name = self._create_extraction_cache(
            transcript,
            run_id=run_id,
            youtube_video_id=youtube_video_id,
            display_name=f"gemma:{youtube_video_id}:{pass_label}",
            model=model,
            system_instruction=system_instruction,
            cache_pass_label=f"{pass_label}_cache",
        )
        if not cache_name:
            return self._failure_envelope(
                run_id,
                f"Gemini cache create failed for pass={pass_label}; "
                f"see p{pass_label}_cache log for details.",
                model=model,
            )
        try:
            return self._call_cached_llm_and_parse(
                cache_name,
                run_id=run_id,
                pass_label=pass_label,
                system_instruction=None,
                user_message=user_message,
                response_schema=response_schema,
                youtube_video_id=youtube_video_id,
                model=model,
            )
        finally:
            self._delete_extraction_cache(cache_name, model=model)

    def _pass_extract(
        self,
        transcript: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        *,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        return self._pass_with_cached_transcript(
            transcript,
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
            ),
            response_schema=ExtractEnvelope,
            model=model,
        )

    def _pass_fact_check(
        self,
        transcript: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        draft_anchors: List[Dict[str, Any]],
        *,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        draft_anchors_json = json.dumps(draft_anchors, ensure_ascii=False, indent=2)
        return self._pass_with_cached_transcript(
            transcript,
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
                draft_anchors_json=draft_anchors_json,
            ),
            response_schema=FactCheckEnvelope,
            model=model,
        )

    def _pass_bullets_and_committee(
        self,
        transcript: str,
        run_id: str,
        youtube_video_id: str,
        meeting_date: str,
        *,
        model: Optional[ModelEnum] = None,
    ) -> Dict[str, Any]:
        return self._pass_with_cached_transcript(
            transcript,
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
    def _timestamp_string_to_seconds(ts: Optional[str]) -> Optional[int]:
        """Parse ``'HH:MM:SS'`` or ``'MM:SS'`` into a total seconds integer.

        Returns ``None`` when the input is empty or doesn't match either
        format — anchors without parseable timestamps still persist; only
        the ``timestamp_seconds`` column ends up NULL.
        """
        if not ts or not isinstance(ts, str):
            return None
        parts = ts.strip().split(":")
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
    def _build_text_to_embed(
        anchor: Dict[str, Any], meeting_date: str, committee: str
    ) -> str:
        """Format a single anchor as one line suitable for vector embedding.

        Pattern: ``Date: {date} | Committee: {committee} | Topic: {headline} | Fact: {text}``
        """
        return (
            f"Date: {meeting_date} | "
            f"Committee: {committee} | "
            f"Topic: {anchor.get('anchor_headline', '')} | "
            f"Fact: {anchor.get('anchor_text', '')}"
        )

    def _stitch_anchor(
        self, raw: Dict[str, Any], meeting_date: str, committee: str
    ) -> Dict[str, Any]:
        """Combine raw LLM-emitted anchor with locally-computed fields."""
        ts_seconds = self._timestamp_string_to_seconds(raw.get("timestamp_string"))
        return {
            **raw,
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
