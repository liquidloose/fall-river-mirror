"""
Pydantic response schemas for Gemini ``response_schema``-constrained calls.

These models define the shape that each extractor pass expects back from
Gemini. The ``google-genai`` SDK serializes a Pydantic class to JSON Schema
under the hood when passed as ``GenerateContentConfig.response_schema``,
and Gemini enforces the shape on the model's output. The returned response
exposes a ``.parsed`` attribute that is the Pydantic instance.

Conventions for this slice:

- :class:`FactualAnchorItem` deliberately omits ``timestamp_seconds`` and
  ``text_to_embed``: those are computed locally in
  :class:`~app.agent_kit.agents.extractors.gemma_nye.GemmaNye` after the
  Gemini calls return, not asked of the model. Asking the model to do
  string-to-seconds math is wasteful and error-prone.
- :class:`FactCheckEnvelope` carries the same ``factual_anchor_items``
  shape as :class:`ExtractEnvelope`. Pass 3 emits the full corrected list,
  not sparse diffs, so merging is a single assignment.
- :class:`BulletsAndCommittee` constrains the committee classification to
  the :class:`~app.data.enum_classes.Committee` enum, so any value Gemini
  emits is guaranteed to round-trip through the persistence layer.
"""

from typing import List

from pydantic import BaseModel, Field

from app.data.enum_classes import Committee, RollCallType


class FactualAnchorItem(BaseModel):
    """One factual anchor pulled from a meeting transcript.

    ``timestamp_string`` is whatever marker the transcript uses (``"01:15:30"``
    or ``"75:10"``); :class:`GemmaNye` parses it locally to ``timestamp_seconds``.
    """

    timestamp_string: str = Field(
        description="Wall-clock timestamp of the moment in the transcript, "
        "e.g. '01:15:30' or '75:10'."
    )
    anchor_headline: str = Field(
        description="Short, factual one-line headline summarizing this anchor."
    )
    anchor_text: str = Field(
        description="One- to three-sentence factual description of what happened."
    )
    has_official_vote: bool = Field(
        description="True if the anchor corresponds to a formal decision of the "
        "body — voice vote, hand vote, recorded vote, consensus, or motion "
        "passed by acclamation. When `roll_call_type='voting'`, this MUST be True."
    )
    roll_call_type: RollCallType = Field(
        description="Which kind of roll call (if any) this anchor captures. "
        "`none` for ordinary discussion or non-roll-call decisions. "
        "`attendance` only when members were called by name to record "
        "present/absent (clerk-led roll call) — not chair introductions "
        "or a bare quorum statement. "
        "`voting` when the formal decision was resolved by a recorded "
        "named-member roll-call vote (each member's yea/nay/abstain "
        "individually recorded); this value implies `has_official_vote=True`. "
        "The three values are mutually exclusive."
    )


class ExtractEnvelope(BaseModel):
    """Pass-2 draft output: anchors only, no bullets, no classification."""

    factual_anchor_items: List[FactualAnchorItem]


class FactCheckedAnchorItem(FactualAnchorItem):
    """A factual anchor that has been through the fact-check pass.

    Extends :class:`FactualAnchorItem` with ``fact_check_note`` — a per-anchor
    audit field that the fact-check pass uses to record what was wrong with
    the original draft. The corrected, vector-ready factual statement always
    lives in ``anchor_text``; ``fact_check_note`` is a separate string used to
    track common model mistakes so prompt iteration can target them. It is
    NEVER concatenated into ``anchor_text`` and is NEVER embedded.
    """

    fact_check_note: str = Field(
        default="",
        description="Brief description of what was wrong with the draft anchor "
        "this entry is correcting. Empty string when the draft was re-emitted "
        "unchanged. NEVER restate the corrected facts here — those go in "
        "`anchor_text`. Use this field only for the discrepancy itself, e.g. "
        "'Draft said vote passed 7-2; transcript shows the motion was tabled.' "
        "or 'Draft anchor_headline misnamed Councilor; corrected to use full "
        "name from transcript.'",
    )


class RemovedDraftAnchor(BaseModel):
    """A draft anchor the fact-check pass concluded was fabricated and dropped.

    Removed drafts are intentionally NOT written into the ``anchors`` table —
    the anchors table is the canonical RAG/vector-store source and must stay
    factual. Removals live in a separate ``fact_check_removals`` audit table
    so prompt iteration can mine the model's hallucination patterns without
    polluting retrieval.

    A "fabricated" anchor is one whose described event does not occur anywhere
    in the cached transcript — not even loosely. Anchors that describe a real
    event but get the details wrong are CORRECTED (re-emitted in
    ``factual_anchor_items`` with the fix in ``anchor_text`` and the
    discrepancy in ``fact_check_note``), not removed.
    """

    original_timestamp_string: str = Field(
        description="The `timestamp_string` value the draft anchor claimed. "
        "Copy verbatim from the draft so the audit log preserves what the "
        "model originally produced."
    )
    original_anchor_headline: str = Field(
        description="The `anchor_headline` value the draft anchor claimed. "
        "Copy verbatim from the draft."
    )
    original_anchor_text: str = Field(
        description="The `anchor_text` value the draft anchor claimed. Copy "
        "verbatim from the draft."
    )
    removal_reason: str = Field(
        description="One short factual sentence explaining why this draft "
        'was dropped — typically `"No corresponding event found in the '
        'cached transcript at or near this timestamp."` or similar. Do not '
        "restate the corrected facts here; removals have no replacement."
    )


class FactCheckEnvelope(BaseModel):
    """Pass-3 corrected output.

    ``factual_anchor_items`` is a FULL re-emit of the corrected anchor list
    (no sparse diffs). ``removed_drafts`` is the audit list of draft anchors
    that the fact-check pass concluded were fabricated and dropped from the
    corrected list. Empty list is the normal case.
    """

    factual_anchor_items: List[FactCheckedAnchorItem]
    removed_drafts: List[RemovedDraftAnchor]


class BulletsAndCommittee(BaseModel):
    """Pass-4 output: 5-8 executive bullets plus single committee classification."""

    primary_committee: Committee = Field(
        description="The committee or board that owned this meeting, chosen "
        "from the canonical Committee enum."
    )
    executive_summary_bullets: List[str] = Field(
        min_length=5,
        max_length=8,
        description="5 to 8 high-impact bullets that tease the article "
        "without spoiling its conclusions.",
    )
