from typing import Any, Dict

from app.agent_kit.agents.extractors.base_extractor import BaseExtractor


class GemmaNye(BaseExtractor):
    """
    Gemma Nye — Fall River meeting-data extractor.

    Reads council and committee transcripts and emits a structured JSON
    envelope of factual anchors for downstream RAG retrieval and prose
    journalists. Pinned to Gemini via :attr:`BaseExtractor.PROVIDER`.

    Operational content lives in markdown, not Python:

    - Character / background → ``context_files/bios/gemma_nye_bio.md``
    - One-line summary → ``context_files/descriptions/gemma_nye_description.md``
    - Behavioral guardrails / extraction rules →
      ``context_files/system_instructions/gemma_nye_system_instructions.md``
    - Per-call payload template →
      ``context_files/user_prompts/gemma_nye_user_prompt.md``

    The class itself only owns identity traits and the
    :meth:`extract` call signature.
    """

    FIRST_NAME = "Gemma"
    LAST_NAME = "Nye"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    # SLANT and STYLE describe Gemma's methodology, not political angle / prose voice.
    SLANT = "neutral"
    STYLE = "structured"

    def extract(
        self,
        transcript: str,
        youtube_video_id: str,
        meeting_date: str,
        primary_committee: str,
    ) -> Dict[str, Any]:
        """
        Extract structured factual anchors from a Fall River meeting transcript.

        Args:
            transcript: Full transcript text. The system instruction expects
                ``[timestamp_seconds]`` markers inline; pass them through
                verbatim — do not strip them before sending.
            youtube_video_id: 11-character YouTube id. Acts as the meeting's
                stable, globally unique identifier and is the FK that
                ``anchors`` rows carry back to ``transcripts``.
            meeting_date: ISO 8601 date (YYYY-MM-DD) of the meeting.
            primary_committee: Canonical committee or board name (e.g.
                ``"Land Use & Zoning Board"``, ``"City Council"``).

        Returns:
            Result envelope per :meth:`BaseExtractor._call_llm_and_parse`:
            ``{"provider", "model", "run_id", "success", "message", "data"}``.
            ``run_id`` is a fresh UUID per call and is the FK callers stamp
            onto ``anchors`` rows when persisting the envelope. While the
            Gemini integration is unwired, every call returns
            ``success=False`` with a 501-shaped message from
            :meth:`LLMTextQuery.get_raw_response`; a debug log file is still
            written under ``logs/extractions/`` so the failure is traceable.
        """
        system_instruction = self.get_system_instruction()
        user_message = self._render_user_prompt(
            youtube_video_id=youtube_video_id,
            meeting_date=meeting_date,
            primary_committee=primary_committee,
            transcript=transcript,
        )
        return self._call_llm_and_parse(
            system_instruction,
            user_message,
            youtube_video_id=youtube_video_id,
        )
