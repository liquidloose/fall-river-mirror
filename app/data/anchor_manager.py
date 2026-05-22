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
  the fact-check pass, anchors may also carry ``fact_check_note`` — a
  per-anchor uncertainty caveat populated only when the model wants to flag
  self-doubt about the anchor's content. The caveat is stored on its own
  column for SQL-queryable access AND the extractor appends it into
  ``text_to_embed`` (see ``GemmaNye._build_text_to_embed``) so downstream
  RAG queries see the caveat alongside the fact. AnchorManager just
  persists whatever ``text_to_embed`` the extractor produced; it does not
  re-stitch. Confident anchors get NULL/empty here and the base
  ``text_to_embed`` is used unchanged. The legacy boolean roll-call
  columns (``has_official_roll_call``, ``has_voting_roll_call``,
  ``has_attendance_roll_call``) are left at their DB default (0) for new
  rows and are no longer written from the envelope; they remain on the
  table only to keep historical rows readable.
- ``executive_summary``: one row per ``executive_summary_bullets[i]`` string.
  Timestamps and headline are NULL; the bullet text fills both ``anchor_text``
  and ``text_to_embed``; ``has_official_vote=0``, ``roll_call_type='none'``,
  and ``fact_check_note`` is NULL.

FACT-CHECK AUDIT TABLE (`fact_check_removals`)
---------------------------------------------
Fact-check envelopes may also carry a ``fact_check_audit`` list — every draft
the fact-check pass removed, corrected, or added. Those rows are written to
the ``fact_check_removals`` table (kept under that name even though the
scope is broader than removals now) — NEVER to ``anchors`` — so the
canonical RAG/vector-store source stays clean of audit metadata. Each row
is correlated with its extractor run via ``run_id`` (shared with
``anchors.run_id``); rows with ``kind in ('corrected','added')`` additionally
carry ``anchor_id`` linking to the resulting ``anchors.id`` row. The
``audit_note`` column is an uncertainty caveat about the fact-check
DECISION (e.g. "removal might be wrong; ambiguous transcript section") —
populated only when the model wants a human reviewer to look. Bulk
error-pattern queries inspect the structural fields (``kind``, originals,
joined ``anchor_text``); ``audit_note`` is a human-review flag only.

RUN SCOPING
-----------
A single extractor invocation writes N anchor rows that all share the same
``run_id`` UUID, so the rows are coherent across the table. Re-extracting the
same transcript later produces a new ``run_id`` and a new set of rows; both
runs coexist (no overwrite). Audit rows from the same run also share that
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
                        "fact_check_audit": [
                            {
                                "kind": "removed",
                                "original_timestamp_string": "00:45:12",
                                "original_anchor_headline": "...",
                                "original_anchor_text": "...",
                                "corrected_anchor_text": null,
                                "audit_note": ""
                            },
                            {
                                "kind": "corrected",
                                "original_timestamp_string": "00:30:01",
                                "original_anchor_headline": "...",
                                "original_anchor_text": "...",
                                "corrected_anchor_text": "<verbatim copy of corrected factual_anchor_items[i].anchor_text>",
                                "audit_note": ""
                            },
                            {
                                "kind": "added",
                                "original_timestamp_string": null,
                                "original_anchor_headline": null,
                                "original_anchor_text": null,
                                "corrected_anchor_text": "<verbatim copy of new factual_anchor_items[i].anchor_text>",
                                "audit_note": ""
                            }
                        ]
                    }

                Missing keys are treated as empty lists. Per-item fields
                read defensively: ``anchor_text`` and ``text_to_embed`` are
                required on factual anchors; everything else falls back to
                NULL / 0. ``fact_check_audit`` is present only on
                fact-check envelopes; entries are validated per ``kind``:

                - ``kind='removed'`` requires non-empty
                  ``original_anchor_text``; ``anchor_id`` is left NULL.
                - ``kind='corrected'`` requires non-empty
                  ``original_anchor_text`` AND non-empty
                  ``corrected_anchor_text``. ``anchor_id`` is looked up
                  from the corrected-text -> ``anchors.id`` map captured
                  during this call's factual-anchor insert loop.
                - ``kind='added'`` requires non-empty
                  ``corrected_anchor_text``; originals are stored as NULL.
                - Unknown ``kind`` values are skipped with WARN.
                - Corrected/added entries whose ``corrected_anchor_text``
                  does not match any just-inserted anchor are skipped
                  with WARN (orphan audit row guard).
                - ``audit_note`` is stripped and stored as NULL when
                  empty / whitespace.
            extractor_name: Name string (e.g. ``"Gemma Nye"``) written to
                every row's ``extractor_name`` column for provenance.
            model: Provider model id (e.g. ``"gemini-2.0-pro"``); written to
                every row's ``model`` column. May be ``None``.

        Returns:
            Total number of rows inserted across BOTH tables: factual anchors
            + summary bullets in ``anchors``, plus audit-entry rows in
            ``fact_check_removals`` (one per removal/correction/addition).

        Raises:
            Exception: Any DB error during the insert batch triggers a full
                rollback and re-raises. Callers see the original SQLite
                exception so they can log / surface it.
        """
        bullets: List[str] = list(envelope.get("executive_summary_bullets") or [])
        anchors: List[Dict[str, Any]] = list(envelope.get("factual_anchor_items") or [])
        fact_check_audit: List[Dict[str, Any]] = list(envelope.get("fact_check_audit") or [])
        created_at = datetime.now(timezone.utc).isoformat()
        rows_inserted = 0

        # Legacy boolean roll-call columns (has_official_roll_call,
        # has_voting_roll_call, has_attendance_roll_call) are intentionally
        # omitted from this INSERT; they stay at their DB default of 0 for new
        # rows. Roll-call semantics for new rows live in `roll_call_type`.
        # `fact_check_note` is the anchor-level uncertainty caveat, populated
        # only when the fact-check pass flagged self-doubt (NULL otherwise).
        # The extractor has already appended a non-empty note into
        # `text_to_embed` upstream — we just persist whatever the envelope
        # produced.
        insert_sql = """
            INSERT INTO anchors (
                youtube_id, run_id, doc_type,
                timestamp_string, timestamp_seconds, anchor_headline,
                anchor_text, has_official_vote, roll_call_type,
                fact_check_note,
                text_to_embed, extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Unified fact-check audit insert. One row per removal / correction /
        # addition. Lives in the `fact_check_removals` table (kept under
        # that name even though scope is broader than removals). `anchor_id`
        # is NULL for kind='removed' and the resulting anchors.id for
        # kind in ('corrected','added').
        audit_insert_sql = """
            INSERT INTO fact_check_removals (
                youtube_id, run_id, kind, anchor_id,
                original_timestamp_string, original_anchor_headline,
                original_anchor_text, audit_note,
                extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Whitelist for `roll_call_type` — mirrors RollCallType enum values.
        # Anything unrecognized falls back to 'none' so a malformed model
        # response can't corrupt the column with an unknown enum string.
        ALLOWED_ROLL_CALL_TYPES = {"none", "attendance", "voting"}
        ALLOWED_AUDIT_KINDS = {"removed", "corrected", "added"}

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

        # Built during the factual-anchor insert loop; consumed by the audit
        # loop to fill `anchor_id` for kind='corrected' and kind='added'.
        # Keyed by `anchor_text` because that's what the LLM emits in
        # `corrected_anchor_text` as the join handle (LLM has no PKs).
        corrected_text_to_anchor_id: Dict[str, int] = {}

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
                # Capture the just-inserted row id so a later audit entry
                # whose `corrected_anchor_text` matches this anchor_text can
                # fill `anchor_id`. If the model emits duplicate anchor_text
                # values (rare; arguably its own bug to flag), the last one
                # wins here — the audit row will link to the last instance.
                lastrowid = self.database.cursor.lastrowid
                if isinstance(lastrowid, int):
                    corrected_text_to_anchor_id[anchor_text] = lastrowid
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

            audit_counts = {"removed": 0, "corrected": 0, "added": 0}
            for entry in fact_check_audit:
                raw_kind = entry.get("kind")
                kind = raw_kind if isinstance(raw_kind, str) else None
                if kind not in ALLOWED_AUDIT_KINDS:
                    logger.warning(
                        "AnchorManager: skipping fact_check_audit entry with "
                        "unknown kind=%r (run_id=%s)",
                        raw_kind,
                        run_id,
                    )
                    continue

                original_text_raw = entry.get("original_anchor_text")
                original_text = original_text_raw.strip() if isinstance(original_text_raw, str) else None
                corrected_text_raw = entry.get("corrected_anchor_text")
                corrected_text = corrected_text_raw.strip() if isinstance(corrected_text_raw, str) else None

                anchor_id: Optional[int] = None
                if kind == "removed":
                    if not original_text:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=removed "
                            "with empty original_anchor_text (run_id=%s, "
                            "original_timestamp_string=%r)",
                            run_id,
                            entry.get("original_timestamp_string"),
                        )
                        continue
                elif kind == "corrected":
                    if not original_text:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=corrected "
                            "with empty original_anchor_text (run_id=%s)",
                            run_id,
                        )
                        continue
                    if not corrected_text:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=corrected "
                            "with empty corrected_anchor_text (run_id=%s, "
                            "original_anchor_text=%r)",
                            run_id,
                            original_text,
                        )
                        continue
                    anchor_id = corrected_text_to_anchor_id.get(corrected_text)
                    if anchor_id is None:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=corrected "
                            "with corrected_anchor_text not found among inserted "
                            "anchors (orphan audit row guard) (run_id=%s, "
                            "corrected_anchor_text=%r)",
                            run_id,
                            corrected_text,
                        )
                        continue
                else:  # kind == "added"
                    if not corrected_text:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=added "
                            "with empty corrected_anchor_text (run_id=%s)",
                            run_id,
                        )
                        continue
                    anchor_id = corrected_text_to_anchor_id.get(corrected_text)
                    if anchor_id is None:
                        logger.warning(
                            "AnchorManager: skipping fact_check_audit kind=added "
                            "with corrected_anchor_text not found among inserted "
                            "anchors (orphan audit row guard) (run_id=%s, "
                            "corrected_anchor_text=%r)",
                            run_id,
                            corrected_text,
                        )
                        continue
                    # Originals are intentionally NULL for added rows.
                    original_text = None

                raw_audit_note = entry.get("audit_note")
                audit_note = (
                    raw_audit_note.strip()
                    if isinstance(raw_audit_note, str) and raw_audit_note.strip()
                    else None
                )

                original_timestamp = (
                    entry.get("original_timestamp_string") if kind != "added" else None
                )
                original_headline = (
                    entry.get("original_anchor_headline") if kind != "added" else None
                )

                self.database.cursor.execute(
                    audit_insert_sql,
                    (
                        youtube_id,
                        run_id,
                        kind,
                        anchor_id,
                        original_timestamp,
                        original_headline,
                        original_text,
                        audit_note,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                audit_counts[kind] += 1
                rows_inserted += 1

            audit_total = sum(audit_counts.values())
            self.database.conn.commit()
            logger.info(
                "AnchorManager: inserted %d anchor row(s) and %d audit row(s) "
                "(removed=%d corrected=%d added=%d) for youtube_id=%s run_id=%s",
                rows_inserted - audit_total,
                audit_total,
                audit_counts["removed"],
                audit_counts["corrected"],
                audit_counts["added"],
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
