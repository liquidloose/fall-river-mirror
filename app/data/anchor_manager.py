"""
Persistence for anchor rows — the RAG-ready chunks emitted by extractors
(e.g. Gemma Nye) into the ``anchors`` table — plus the fact-check audit
sibling table ``fact_check_removals``.

ANCHORS TABLE
-------------
Two row types share the same schema and live in the same table, distinguished
by ``doc_type``:

- ``factual_anchor``: one row per ``factual_anchor_items[i]`` in the envelope.
  Carries timestamp + headline + ``has_official_vote`` + ``roll_call_type``
  (enum: ``'none' | 'attendance' | 'voting'``). When the envelope comes from
  the fact-check pass, anchors may also carry ``fact_check_note`` — a brief
  description of what was wrong with the draft, stored separately from
  ``anchor_text`` so it is never embedded into the vector store. The legacy
  boolean roll-call columns (``has_official_roll_call``,
  ``has_voting_roll_call``, ``has_attendance_roll_call``) are left at their
  DB default (0) for new rows and are no longer written from the envelope;
  they remain on the table only to keep historical rows readable.
- ``executive_summary``: one row per ``executive_summary_bullets[i]`` string.
  Timestamps and headline are NULL; the bullet text fills both ``anchor_text``
  and ``text_to_embed``; ``has_official_vote=0``, ``roll_call_type='none'``,
  and ``fact_check_note`` is NULL.

FACT-CHECK REMOVALS TABLE
-------------------------
Fact-check envelopes may also carry a ``removed_drafts`` list — draft anchors
the fact-check pass concluded were fabricated and dropped from the corrected
list. Those rows are written to the separate ``fact_check_removals`` table
(NEVER to ``anchors``) so the canonical RAG/vector-store source stays
factual. Removals are correlated with their extractor run via ``run_id``
(shared with ``anchors.run_id``).

RUN SCOPING
-----------
A single extractor invocation writes N anchor rows that all share the same
``run_id`` UUID, so the rows are coherent across the table. Re-extracting the
same transcript later produces a new ``run_id`` and a new set of rows; both
runs coexist (no overwrite). Removals from the same run also share that
``run_id`` in ``fact_check_removals``.

Foreign key is ``anchors.youtube_id`` -> ``transcripts.youtube_id`` (the
globally unique YouTube video id), not the SQLite ``transcripts.id`` row, so
rows survive a transcripts table rebuild without orphaning.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .create_database import Database

logger = logging.getLogger(__name__)


class AnchorManager:
    """
    Manages anchor rows in the database.

    The single public write method, :meth:`insert_from_envelope`, performs a
    transactional N-row insert from a parsed extractor envelope. On any
    failure the whole batch rolls back, so the table never holds a partial
    extraction.
    """

    def __init__(self, database: Database):
        self.database = database

    def insert_from_envelope(
        self,
        *,
        youtube_id: str,
        run_id: str,
        envelope: Dict[str, Any],
        extractor_name: str,
        model: Optional[str],
    ) -> int:
        """
        Insert all chunks from one extractor envelope as anchor rows.

        Args:
            youtube_id: YouTube video id of the source meeting; written to
                every row's ``youtube_id`` column (FK to transcripts).
            run_id: UUID identifying this extractor invocation; written to
                every row's ``run_id`` column so the batch can be grouped
                or re-run-compared later.
            envelope: Parsed JSON envelope from the extractor. Expected shape::

                    {
                        "executive_summary_bullets": ["...", "..."],
                        "factual_anchor_items": [
                            {
                                "timestamp_string": "01:15:30",
                                "timestamp_seconds": 4530,
                                "anchor_headline": "...",
                                "anchor_text": "...",
                                "has_official_vote": true,
                                "roll_call_type": "voting",
                                "fact_check_note": "",
                                "text_to_embed": "..."
                            }
                        ],
                        "removed_drafts": [
                            {
                                "original_timestamp_string": "00:45:12",
                                "original_anchor_headline": "...",
                                "original_anchor_text": "...",
                                "removal_reason": "No corresponding event in transcript."
                            }
                        ]
                    }

                Missing keys are treated as empty lists. Per-item fields
                read defensively: ``anchor_text`` and ``text_to_embed`` are
                required on factual anchors; everything else falls back to
                NULL / 0. ``removed_drafts`` is present only on fact-check
                envelopes; entries with empty ``original_anchor_text`` or
                empty ``removal_reason`` are skipped with a WARN log.
            extractor_name: Name string (e.g. ``"Gemma Nye"``) written to
                every row's ``extractor_name`` column for provenance.
            model: Provider model id (e.g. ``"gemini-2.0-pro"``); written to
                every row's ``model`` column. May be ``None``.

        Returns:
            Total number of rows inserted across BOTH tables: factual anchors
            + summary bullets in ``anchors``, plus removed-draft rows in
            ``fact_check_removals``.

        Raises:
            Exception: Any DB error during the insert batch triggers a full
                rollback and re-raises. Callers see the original SQLite
                exception so they can log / surface it.
        """
        bullets: List[str] = list(envelope.get("executive_summary_bullets") or [])
        anchors: List[Dict[str, Any]] = list(envelope.get("factual_anchor_items") or [])
        removed_drafts: List[Dict[str, Any]] = list(envelope.get("removed_drafts") or [])
        created_at = datetime.now(timezone.utc).isoformat()
        rows_inserted = 0

        # Legacy boolean roll-call columns (has_official_roll_call,
        # has_voting_roll_call, has_attendance_roll_call) are intentionally
        # omitted from this INSERT; they stay at their DB default of 0 for new
        # rows. Roll-call semantics for new rows live in `roll_call_type`.
        # `fact_check_note` is populated only when the envelope carries one
        # (fact-check pass); extract-pass anchors get NULL here.
        insert_sql = """
            INSERT INTO anchors (
                youtube_id, run_id, doc_type,
                timestamp_string, timestamp_seconds, anchor_headline,
                anchor_text, has_official_vote, roll_call_type,
                fact_check_note,
                text_to_embed, extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Removed-draft rows go to a separate audit table — never to `anchors`,
        # so the canonical vector-store source stays factual.
        removal_insert_sql = """
            INSERT INTO fact_check_removals (
                youtube_id, run_id,
                original_timestamp_string, original_anchor_headline,
                original_anchor_text, removal_reason,
                extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Whitelist for `roll_call_type` — mirrors RollCallType enum values.
        # Anything unrecognized falls back to 'none' so a malformed model
        # response can't corrupt the column with an unknown enum string.
        ALLOWED_ROLL_CALL_TYPES = {"none", "attendance", "voting"}

        def _coerce_roll_call_type(raw: Any) -> str:
            if isinstance(raw, str) and raw in ALLOWED_ROLL_CALL_TYPES:
                return raw
            value = getattr(raw, "value", None)
            if isinstance(value, str) and value in ALLOWED_ROLL_CALL_TYPES:
                return value
            if raw not in (None, ""):
                logger.warning(
                    "AnchorManager: unrecognized roll_call_type=%r; coercing to 'none' "
                    "(run_id=%s)",
                    raw,
                    run_id,
                )
            return "none"

        try:
            for anchor in anchors:
                anchor_text = anchor.get("anchor_text")
                text_to_embed = anchor.get("text_to_embed") or anchor_text
                if not anchor_text or not text_to_embed:
                    logger.warning(
                        "AnchorManager: skipping factual_anchor with empty "
                        "anchor_text/text_to_embed (run_id=%s, headline=%r)",
                        run_id,
                        anchor.get("anchor_headline"),
                    )
                    continue
                raw_note = anchor.get("fact_check_note")
                fact_check_note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None
                self.database.cursor.execute(
                    insert_sql,
                    (
                        youtube_id,
                        run_id,
                        "factual_anchor",
                        anchor.get("timestamp_string"),
                        anchor.get("timestamp_seconds"),
                        anchor.get("anchor_headline"),
                        anchor_text,
                        1 if anchor.get("has_official_vote") else 0,
                        _coerce_roll_call_type(anchor.get("roll_call_type")),
                        fact_check_note,
                        text_to_embed,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                rows_inserted += 1

            for bullet in bullets:
                bullet_text = (bullet or "").strip() if isinstance(bullet, str) else ""
                if not bullet_text:
                    continue
                self.database.cursor.execute(
                    insert_sql,
                    (
                        youtube_id,
                        run_id,
                        "executive_summary",
                        None,
                        None,
                        None,
                        bullet_text,
                        0,
                        "none",
                        None,
                        bullet_text,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                rows_inserted += 1

            removals_inserted = 0
            for removed in removed_drafts:
                original_text = (removed.get("original_anchor_text") or "").strip()
                reason = (removed.get("removal_reason") or "").strip()
                if not original_text or not reason:
                    logger.warning(
                        "AnchorManager: skipping removed_draft with empty "
                        "original_anchor_text/removal_reason (run_id=%s, "
                        "original_timestamp_string=%r)",
                        run_id,
                        removed.get("original_timestamp_string"),
                    )
                    continue
                self.database.cursor.execute(
                    removal_insert_sql,
                    (
                        youtube_id,
                        run_id,
                        removed.get("original_timestamp_string"),
                        removed.get("original_anchor_headline"),
                        original_text,
                        reason,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                removals_inserted += 1
                rows_inserted += 1

            self.database.conn.commit()
            logger.info(
                "AnchorManager: inserted %d anchor row(s) and %d removed-draft "
                "row(s) for youtube_id=%s run_id=%s",
                rows_inserted - removals_inserted,
                removals_inserted,
                youtube_id,
                run_id,
            )
            return rows_inserted
        except Exception:
            logger.exception(
                "AnchorManager: insert_from_envelope failed; rolling back "
                "(youtube_id=%s run_id=%s)",
                youtube_id,
                run_id,
            )
            self.database.conn.rollback()
            raise
