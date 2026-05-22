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
  shape as :class:`ExtractEnvelope` (extended to :class:`FactCheckedAnchorItem`
  with an uncertainty caveat). Pass 3 emits the full corrected list, not
  sparse diffs, so merging is a single assignment. Audit metadata for any
  removed / corrected / added drafts lives in a parallel
  :class:`FactCheckAuditEntry` list so the canonical anchor list stays
  clean of audit clutter.
- :class:`BulletsAndCommittee` constrains the committee classification to
  the :class:`~app.data.enum_classes.Committee` enum, so any value Gemini
  emits is guaranteed to round-trip through the persistence layer.

Uncertainty model: both :attr:`FactCheckedAnchorItem.fact_check_note` and
:attr:`FactCheckAuditEntry.audit_note` are populated ONLY when the model
wants to flag self-doubt. Confident decisions leave both fields empty.
Silence = confidence; a non-empty note anywhere reads as "human reviewer
should look at this." ``fact_check_note`` rides into the embedding so RAG
queries see the caveat; ``audit_note`` is logged only.
"""

from typing import List, Literal, Optional

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
    uncertainty caveat populated only when the fact-check pass wants to flag
    self-doubt about the anchor's content (e.g. ambiguous timestamp, unsure
    speaker attribution). When populated, the persistence layer appends it
    into ``text_to_embed`` so RAG queries see the caveat alongside the fact;
    confident anchors leave this empty and the caveat segment is omitted.
    """

    fact_check_note: str = Field(
        default="",
        description="Uncertainty caveat about THIS anchor's content. Populate "
        "ONLY when you (the model) are unsure about some part of the anchor "
        "and want a human reviewer to look at it — e.g. "
        "'Timestamp marker was ambiguous; this is the closest match.' or "
        "'Speaker attribution uncertain; transcript could be read two ways.' "
        "Leave EMPTY when you are confident in the anchor as emitted. "
        "Silence here means confidence; downstream RAG embeddings include "
        "this caveat verbatim when populated, so do not put discrepancy "
        "explanations or commentary about the original draft here — only "
        "honest uncertainty about the current anchor's correctness.",
    )


class FactCheckAuditEntry(BaseModel):
    """One row of the fact-check audit log for a removed / corrected / added draft.

    Distinguished by :attr:`kind`. Persistence lands every entry in the
    ``fact_check_removals`` table (kept under that name even though the scope
    is broader than removals now) so bulk prompt-iteration queries can mine
    the model's error patterns across runs without polluting the canonical
    ``anchors`` table.

    Invariants the prompt enforces:

    - ``kind="removed"`` → originals required (verbatim from the draft);
      ``corrected_anchor_text`` MUST be null (no replacement).
    - ``kind="corrected"`` → originals required (verbatim from the draft);
      ``corrected_anchor_text`` MUST equal the corrected anchor's ``anchor_text``
      (verbatim — used by persistence as the join key to fill ``anchor_id``).
    - ``kind="added"`` → originals MUST be null (no draft existed);
      ``corrected_anchor_text`` MUST equal the new anchor's ``anchor_text``.

    ``audit_note`` is silent when the model is confident in the decision.
    """

    kind: Literal["removed", "corrected", "added"] = Field(
        description="What the fact-check pass did with the draft anchor. "
        "`removed`: dropped as fabricated. `corrected`: re-emitted with "
        "fixed details. `added`: spotted a milestone the draft missed."
    )
    original_timestamp_string: Optional[str] = Field(
        default=None,
        description="The `timestamp_string` value the draft anchor claimed. "
        "Copy verbatim from the draft for `kind='removed'` and "
        "`kind='corrected'`. MUST be null for `kind='added'`.",
    )
    original_anchor_headline: Optional[str] = Field(
        default=None,
        description="The `anchor_headline` value the draft anchor claimed. "
        "Copy verbatim from the draft for `kind='removed'` and "
        "`kind='corrected'`. MUST be null for `kind='added'`.",
    )
    original_anchor_text: Optional[str] = Field(
        default=None,
        description="The `anchor_text` value the draft anchor claimed. Copy "
        "verbatim from the draft for `kind='removed'` and `kind='corrected'`. "
        "MUST be null for `kind='added'`.",
    )
    corrected_anchor_text: Optional[str] = Field(
        default=None,
        description="The `anchor_text` of the resulting anchor in "
        "`factual_anchor_items`. Persistence uses this as the join key to "
        "fill `anchor_id`, so it MUST be a verbatim copy of the matching "
        "`factual_anchor_items[i].anchor_text` string. Set for "
        "`kind='corrected'` and `kind='added'`. MUST be null for "
        "`kind='removed'` (no replacement anchor exists).",
    )
    audit_note: str = Field(
        default="",
        description="Uncertainty caveat about THIS fact-check DECISION. "
        "Populate ONLY when you (the model) are unsure your decision was "
        "right — e.g. 'Removal might be wrong; transcript section was "
        "ambiguous about whether this event actually occurred.' or "
        "'Correction unsure; multiple interpretations of the vote count "
        "are possible.' Leave EMPTY when you are confident in the decision. "
        "Silence here means confidence; this field is logged for human "
        "review only and is NEVER embedded into RAG.",
    )


class FactCheckEnvelope(BaseModel):
    """Pass-3 corrected output.

    ``factual_anchor_items`` is a FULL re-emit of the corrected anchor list
    (no sparse diffs). ``fact_check_audit`` is the unified audit log of every
    draft the pass removed, corrected, or added; empty list is the normal
    case when every draft was re-emitted unchanged. The two lists are
    independent — unchanged drafts produce a `factual_anchor_items` entry
    but NO audit entry.
    """

    factual_anchor_items: List[FactCheckedAnchorItem]
    fact_check_audit: List[FactCheckAuditEntry]


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
