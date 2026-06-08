"""
Persistence for anchor rows — the RAG-ready chunks emitted by extractors
(e.g. Gemma Nye) into the ``anchors`` table — plus the fact-check audit
sibling table ``fact_check_removals`` and the spelling-corrections audit
sibling table ``spelling_corrections``.

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
the fact-check pass removed, corrected, added, or left unresolved. Those
rows are written to the ``fact_check_removals`` table (kept under that name
even though the scope is broader than removals now) — NEVER to ``anchors`` —
so the canonical RAG/vector-store source stays clean of audit metadata. Each
row is correlated with its extractor run via ``run_id`` (shared with
``anchors.run_id``); rows with ``kind in ('corrected','added','unresolved')``
additionally carry ``anchor_id`` linking to the resulting ``anchors.id`` row.
The ``audit_note`` column is REQUIRED on every LLM-emitted entry and
describes the issue found (what was wrong, missing, or unverifiable); for
``kind='unresolved'`` that same note is later surfaced to readers as an
"AI Editor's note". Bulk error-pattern queries inspect the structural fields
(``kind``, originals, joined ``anchor_text``) alongside ``audit_note``.

This method ALSO writes two system-synthesized kinds that the LLM never
emits: ``rejected_anchor`` (a factual anchor or bullet was dropped for empty
text) and ``rejected_audit`` (a ``fact_check_audit`` entry failed validation
— unknown kind, missing required field, orphan ``corrected_anchor_text``, or
empty ``audit_note``). Their ``audit_note`` carries a system-generated reason
and a JSON snippet of the offending entry, so a rising rejection count is a
direct signal of prompt/context drift. ``anchor_id`` is always NULL for these.

SPELLING-CORRECTIONS AUDIT TABLE (`spelling_corrections`)
---------------------------------------------------------
Pass-4 spell-check envelopes carry a ``spelling_corrections`` list — one row
per canonical-name spelling fix the pass applied to an anchor or bullet.
Those rows land in the ``spelling_corrections`` table (parallel to
``fact_check_removals``; never alongside ``anchors``). Each row carries
``target_kind`` (``'factual_anchor' | 'executive_summary'``) and an
``anchor_id`` linking to the resulting ``anchors.id`` row — both factual
and summary rows live in ``anchors``, so the join works for both. The join
key during insert is ``corrected_anchor_text``: for ``factual_anchor`` it
matches against the post-pass-4 ``anchor_text`` we just inserted; for
``executive_summary`` it matches against the bullet string. Multiple
spelling fixes per anchor produce multiple rows that all link to the same
``anchor_id``. ``audit_note`` is an uncertainty caveat about the
CORRECTION (e.g. "ambiguous transcript context; could also be a private
citizen"), populated only when the model wants a human reviewer to look.

RUN SCOPING
-----------
A single extractor invocation writes N anchor rows that all share the same
``run_id`` UUID, so the rows are coherent across the table. Re-extracting the
same transcript later produces a new ``run_id`` and a new set of rows; both
runs coexist (no overwrite). Audit rows from the same run also share that
``run_id`` in both ``fact_check_removals`` and ``spelling_corrections``.

Foreign key is ``anchors.youtube_id`` -> ``transcripts.youtube_id`` (the
globally unique YouTube video id), not the SQLite ``transcripts.id`` row, so
rows survive a transcripts table rebuild without orphaning.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .create_database import Database

logger = logging.getLogger(__name__)


def _normalize_anchor_text(text: str) -> str:
    return " ".join(text.split())


def _lookup_anchor_id_for_audit(
    *,
    kind: str,
    entry: Dict[str, Any],
    corrected_text: Optional[str],
    corrected_text_to_anchor_id: Dict[str, int],
    anchor_ids_by_index: List[Optional[int]],
) -> Optional[int]:
    """Resolve ``anchor_id`` for corrected / added / unresolved audit rows."""
    if kind not in ("corrected", "unresolved", "added"):
        return None
    raw_idx = entry.get("factual_anchor_index")
    if isinstance(raw_idx, int) and not isinstance(raw_idx, bool):
        if 0 <= raw_idx < len(anchor_ids_by_index):
            anchor_id = anchor_ids_by_index[raw_idx]
            if anchor_id is not None:
                return anchor_id
    if not corrected_text:
        return None
    anchor_id = corrected_text_to_anchor_id.get(corrected_text)
    if anchor_id is not None:
        return anchor_id
    norm = _normalize_anchor_text(corrected_text)
    for text, candidate_id in corrected_text_to_anchor_id.items():
        if _normalize_anchor_text(text) == norm:
            return candidate_id
    return None


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

    def _sync_unresolved_anchor_caveat(self, anchor_id: int, audit_note: str) -> None:
        """Copy ``audit_note`` onto the anchor when ``fact_check_note`` was left empty."""
        cursor = self.database.cursor
        cursor.execute(
            "SELECT fact_check_note, text_to_embed FROM anchors WHERE id = ?",
            (anchor_id,),
        )
        row = cursor.fetchone()
        if not row:
            return
        existing_note, text_to_embed = row[0], row[1] or ""
        note_empty = not existing_note or not str(existing_note).strip()
        if note_empty:
            cursor.execute(
                "UPDATE anchors SET fact_check_note = ? WHERE id = ?",
                (audit_note, anchor_id),
            )
        if audit_note and "| Caveat:" not in text_to_embed:
            cursor.execute(
                "UPDATE anchors SET text_to_embed = ? WHERE id = ?",
                (f"{text_to_embed} | Caveat: {audit_note}", anchor_id),
            )

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
                                "audit_note": "No corresponding event anywhere in the transcript."
                            },
                            {
                                "kind": "corrected",
                                "original_timestamp_string": "00:30:01",
                                "original_anchor_headline": "...",
                                "original_anchor_text": "...",
                                "corrected_anchor_text": "<verbatim copy of corrected factual_anchor_items[i].anchor_text>",
                                "audit_note": "Draft claimed a 5-4 vote; transcript records 6-3."
                            },
                            {
                                "kind": "added",
                                "original_timestamp_string": null,
                                "original_anchor_headline": null,
                                "original_anchor_text": null,
                                "corrected_anchor_text": "<verbatim copy of new factual_anchor_items[i].anchor_text>",
                                "audit_note": "Transcript records a budget transfer the draft omitted."
                            },
                            {
                                "kind": "unresolved",
                                "original_timestamp_string": "00:52:40",
                                "original_anchor_headline": "...",
                                "original_anchor_text": "...",
                                "corrected_anchor_text": "<verbatim copy of the kept factual_anchor_items[i].anchor_text>",
                                "audit_note": "The vote count could not be verified; audio was unclear at this point."
                            }
                        ],
                        "spelling_corrections": [
                            {
                                "target_kind": "factual_anchor",
                                "corrected_anchor_text": "<verbatim copy of post-pass-4 factual_anchor_items[i].anchor_text>",
                                "original_term": "Kugan",
                                "corrected_term": "Coogan",
                                "audit_note": ""
                            },
                            {
                                "target_kind": "executive_summary",
                                "corrected_anchor_text": "<verbatim copy of post-pass-4 executive_summary_bullets[j]>",
                                "original_term": "Cumara",
                                "corrected_term": "Camara",
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
                - ``kind='corrected'`` and ``kind='unresolved'`` require
                  non-empty ``original_anchor_text``. ``anchor_id`` is resolved
                  via ``factual_anchor_index`` (preferred), then
                  ``corrected_anchor_text`` exact/normalized match.
                - ``kind='added'`` links via the same index/text lookup;
                  originals are stored as NULL.
                - ``audit_note`` is REQUIRED on every entry. Empty / missing
                  notes, unknown ``kind`` values, missing required fields,
                  and orphan ``corrected_anchor_text`` (not matching any
                  just-inserted anchor) do NOT silently drop: each is recorded
                  as a ``rejected_audit`` row whose ``audit_note`` explains the
                  rejection and embeds a JSON snippet of the offending entry.
                - Factual anchors / bullets with empty text are recorded as
                  ``rejected_anchor`` rows (instead of being silently skipped).

                ``spelling_corrections`` is present only on pass-4 spell-check
                envelopes; entries are validated per ``target_kind``:

                - ``target_kind='factual_anchor'`` looks up ``anchor_id`` in
                  the corrected-text -> ``anchors.id`` map captured during
                  the factual-anchor insert loop.
                - ``target_kind='executive_summary'`` looks up ``anchor_id``
                  in a parallel bullet-text -> ``anchors.id`` map captured
                  during the bullet insert loop.
                - Unknown ``target_kind`` values are skipped with WARN.
                - Entries whose ``corrected_anchor_text`` does not match any
                  just-inserted anchor / bullet row are skipped with WARN
                  (orphan audit row guard).
                - Entries with empty/whitespace ``original_term`` or
                  ``corrected_term`` are skipped with WARN.
                - Entries where ``original_term == corrected_term`` (no-op
                  corrections) are skipped with WARN.
                - ``audit_note`` is stripped and stored as NULL when
                  empty / whitespace.
            extractor_name: Name string (e.g. ``"Gemma Nye"``) written to
                every row's ``extractor_name`` column for provenance.
            model: Provider model id (e.g. ``"gemini-2.0-pro"``); written to
                every row's ``model`` column. May be ``None``.

        Returns:
            Total number of rows inserted across all three tables: factual
            anchors + summary bullets in ``anchors``, audit-entry rows in
            ``fact_check_removals`` (one per removal/correction/addition),
            and spelling-correction rows in ``spelling_corrections`` (one
            per fix applied).

        Raises:
            Exception: Any DB error during the insert batch triggers a full
                rollback and re-raises. Callers see the original SQLite
                exception so they can log / surface it.
        """
        bullets: List[str] = list(envelope.get("executive_summary_bullets") or [])
        anchors: List[Dict[str, Any]] = list(envelope.get("factual_anchor_items") or [])
        fact_check_audit: List[Dict[str, Any]] = list(envelope.get("fact_check_audit") or [])
        spelling_corrections: List[Dict[str, Any]] = list(envelope.get("spelling_corrections") or [])
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

        # Spelling-corrections audit insert. One row per canonical-name
        # spelling fix the pass-4 spell-check applied to an anchor or bullet.
        # `anchor_id` always links back to `anchors.id` — for both factual
        # and summary rows, since bullets are persisted as `executive_summary`
        # rows in the `anchors` table.
        spelling_corrections_insert_sql = """
            INSERT INTO spelling_corrections (
                youtube_id, run_id, anchor_id, target_kind,
                original_term, corrected_term, audit_note,
                extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Whitelist for `roll_call_type` — mirrors RollCallType enum values.
        # Anything unrecognized falls back to 'none' so a malformed model
        # response can't corrupt the column with an unknown enum string.
        ALLOWED_ROLL_CALL_TYPES = {"none", "attendance", "voting"}
        # LLM-emitted fact-check decisions. `unresolved` keeps the anchor but
        # records that the transcript could neither confirm nor refute it.
        ALLOWED_AUDIT_KINDS = {"removed", "corrected", "added", "unresolved"}
        ALLOWED_SPELLING_TARGET_KINDS = {"factual_anchor", "executive_summary"}
        # System-synthesized audit kinds (never emitted by the LLM). Written
        # by this method when persistence rejects malformed output, so a
        # rising count signals prompt/context drift worth investigating.
        REJECTED_ANCHOR_KIND = "rejected_anchor"  # bad factual anchor / bullet
        REJECTED_AUDIT_KIND = "rejected_audit"  # bad fact_check_audit entry

        # Per-kind tally covering LLM decisions plus rejections. Defined here
        # (before the insert loops) so the anchor loop can record rejections
        # for empty anchors before the audit loop runs.
        audit_counts = {
            "removed": 0,
            "corrected": 0,
            "added": 0,
            "unresolved": 0,
            REJECTED_ANCHOR_KIND: 0,
            REJECTED_AUDIT_KIND: 0,
        }

        def _insert_rejection(
            rejection_kind: str,
            note: str,
            *,
            timestamp: Optional[str] = None,
            headline: Optional[str] = None,
            original_text: Optional[str] = None,
        ) -> None:
            """Record a persistence rejection as a ``fact_check_removals`` row.

            ``anchor_id`` is always NULL (nothing was successfully saved).
            ``audit_note`` carries a system-generated reason describing which
            validation rule rejected the row.
            """
            nonlocal rows_inserted
            self.database.cursor.execute(
                audit_insert_sql,
                (
                    youtube_id,
                    run_id,
                    rejection_kind,
                    None,
                    timestamp,
                    headline,
                    original_text,
                    note,
                    extractor_name,
                    model,
                    created_at,
                ),
            )
            audit_counts[rejection_kind] += 1
            rows_inserted += 1

        def _entry_snippet(entry: Dict[str, Any]) -> str:
            """Compact, length-capped JSON snapshot of a rejected entry."""
            try:
                return json.dumps(entry, default=str)[:500]
            except Exception:
                return repr(entry)[:500]

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

        # Built during the factual-anchor insert loop. `anchor_ids_by_index`
        # aligns with envelope `factual_anchor_items` order (None when a row
        # was skipped). `corrected_text_to_anchor_id` is a fallback join on
        # `corrected_anchor_text` when `factual_anchor_index` is missing.
        corrected_text_to_anchor_id: Dict[str, int] = {}
        anchor_ids_by_index: List[Optional[int]] = []
        # Parallel map built during the bullet insert loop; consumed only by
        # the spelling-corrections loop (`target_kind='executive_summary'`)
        # to fill `anchor_id`. Bullets are persisted as `executive_summary`
        # rows where `anchor_text == bullet_text`, so the bullet string is
        # the join key.
        bullet_text_to_anchor_id: Dict[str, int] = {}

        try:
            for anchor in anchors:
                anchor_text = anchor.get("anchor_text")
                text_to_embed = anchor.get("text_to_embed") or anchor_text
                if not anchor_text or not text_to_embed:
                    logger.warning(
                        "AnchorManager: rejecting factual_anchor with empty "
                        "anchor_text/text_to_embed (run_id=%s, headline=%r)",
                        run_id,
                        anchor.get("anchor_headline"),
                    )
                    _insert_rejection(
                        REJECTED_ANCHOR_KIND,
                        "Persistence rejected factual anchor: empty "
                        "anchor_text/text_to_embed.",
                        timestamp=anchor.get("timestamp_string"),
                        headline=anchor.get("anchor_headline"),
                        original_text=(
                            anchor_text if isinstance(anchor_text, str) else None
                        ),
                    )
                    anchor_ids_by_index.append(None)
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
                anchor_id_inserted = lastrowid if isinstance(lastrowid, int) else None
                anchor_ids_by_index.append(anchor_id_inserted)
                if anchor_id_inserted is not None:
                    corrected_text_to_anchor_id[anchor_text] = anchor_id_inserted
                rows_inserted += 1

            for bullet in bullets:
                bullet_text = (bullet or "").strip() if isinstance(bullet, str) else ""
                if not bullet_text:
                    logger.warning(
                        "AnchorManager: rejecting empty executive_summary "
                        "bullet (run_id=%s)",
                        run_id,
                    )
                    _insert_rejection(
                        REJECTED_ANCHOR_KIND,
                        "Persistence rejected executive_summary bullet: "
                        "empty bullet text.",
                    )
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
                # Capture the just-inserted bullet row id so a later
                # spelling-correction entry whose `corrected_anchor_text`
                # matches this bullet can fill `anchor_id`. Duplicate bullet
                # strings (rare; arguably the bullets pass's bug to flag)
                # mean the last one wins here.
                lastrowid = self.database.cursor.lastrowid
                if isinstance(lastrowid, int):
                    bullet_text_to_anchor_id[bullet_text] = lastrowid
                rows_inserted += 1

            for entry in fact_check_audit:
                raw_kind = entry.get("kind")
                kind = raw_kind if isinstance(raw_kind, str) else None
                if kind not in ALLOWED_AUDIT_KINDS:
                    logger.warning(
                        "AnchorManager: rejecting fact_check_audit entry with "
                        "unknown kind=%r (run_id=%s)",
                        raw_kind,
                        run_id,
                    )
                    _insert_rejection(
                        REJECTED_AUDIT_KIND,
                        f"Fact-check audit entry had unknown kind={raw_kind!r}. "
                        f"Entry: {_entry_snippet(entry)}",
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
                            "AnchorManager: rejecting fact_check_audit kind=removed "
                            "with empty original_anchor_text (run_id=%s)",
                            run_id,
                        )
                        _insert_rejection(
                            REJECTED_AUDIT_KIND,
                            "Fact-check audit kind=removed had empty "
                            f"original_anchor_text. Entry: {_entry_snippet(entry)}",
                            timestamp=entry.get("original_timestamp_string"),
                            headline=entry.get("original_anchor_headline"),
                        )
                        continue
                elif kind in ("corrected", "unresolved"):
                    # `unresolved` keeps the anchor unchanged but still links to
                    # it, so structurally it validates exactly like `corrected`.
                    if not original_text:
                        logger.warning(
                            "AnchorManager: rejecting fact_check_audit kind=%s "
                            "with empty original_anchor_text (run_id=%s)",
                            kind,
                            run_id,
                        )
                        _insert_rejection(
                            REJECTED_AUDIT_KIND,
                            f"Fact-check audit kind={kind} had empty "
                            f"original_anchor_text. Entry: {_entry_snippet(entry)}",
                            timestamp=entry.get("original_timestamp_string"),
                            headline=entry.get("original_anchor_headline"),
                        )
                        continue
                    anchor_id = _lookup_anchor_id_for_audit(
                        kind=kind,
                        entry=entry,
                        corrected_text=corrected_text,
                        corrected_text_to_anchor_id=corrected_text_to_anchor_id,
                        anchor_ids_by_index=anchor_ids_by_index,
                    )
                    if anchor_id is None:
                        logger.warning(
                            "AnchorManager: rejecting fact_check_audit kind=%s "
                            "with no matching anchor (index/text lookup failed) "
                            "(run_id=%s)",
                            kind,
                            run_id,
                        )
                        _insert_rejection(
                            REJECTED_AUDIT_KIND,
                            f"Fact-check audit kind={kind} could not be linked to "
                            "an inserted anchor (orphan guard). "
                            f"Entry: {_entry_snippet(entry)}",
                            timestamp=entry.get("original_timestamp_string"),
                            headline=entry.get("original_anchor_headline"),
                            original_text=original_text,
                        )
                        continue
                else:  # kind == "added"
                    anchor_id = _lookup_anchor_id_for_audit(
                        kind=kind,
                        entry=entry,
                        corrected_text=corrected_text,
                        corrected_text_to_anchor_id=corrected_text_to_anchor_id,
                        anchor_ids_by_index=anchor_ids_by_index,
                    )
                    if anchor_id is None:
                        logger.warning(
                            "AnchorManager: rejecting fact_check_audit kind=added "
                            "with no matching anchor (index/text lookup failed) "
                            "(run_id=%s)",
                            run_id,
                        )
                        _insert_rejection(
                            REJECTED_AUDIT_KIND,
                            "Fact-check audit kind=added could not be linked to "
                            "an inserted anchor (orphan guard). "
                            f"Entry: {_entry_snippet(entry)}",
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
                if not audit_note:
                    # Every audit entry must describe the issue it found. A
                    # missing note is malformed output, recorded as a rejection
                    # rather than a silent drop so drift shows up in analysis.
                    logger.warning(
                        "AnchorManager: rejecting fact_check_audit kind=%s with "
                        "empty audit_note (run_id=%s)",
                        kind,
                        run_id,
                    )
                    _insert_rejection(
                        REJECTED_AUDIT_KIND,
                        f"Fact-check audit kind={kind} had empty audit_note "
                        "(every audit entry must describe the issue found). "
                        f"Entry: {_entry_snippet(entry)}",
                        timestamp=entry.get("original_timestamp_string"),
                        headline=entry.get("original_anchor_headline"),
                        original_text=original_text,
                    )
                    continue

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

                if kind == "unresolved" and anchor_id is not None:
                    self._sync_unresolved_anchor_caveat(anchor_id, audit_note)

            spelling_inserted = 0
            for entry in spelling_corrections:
                raw_target = entry.get("target_kind")
                target_kind = raw_target if isinstance(raw_target, str) else None
                if target_kind not in ALLOWED_SPELLING_TARGET_KINDS:
                    logger.warning(
                        "AnchorManager: skipping spelling_corrections entry with "
                        "unknown target_kind=%r (run_id=%s)",
                        raw_target,
                        run_id,
                    )
                    continue

                raw_corrected_text = entry.get("corrected_anchor_text")
                corrected_text = (
                    raw_corrected_text.strip()
                    if isinstance(raw_corrected_text, str)
                    else None
                )
                if not corrected_text:
                    logger.warning(
                        "AnchorManager: skipping spelling_corrections entry with "
                        "empty corrected_anchor_text (run_id=%s, target_kind=%s)",
                        run_id,
                        target_kind,
                    )
                    continue

                raw_original = entry.get("original_term")
                original_term = (
                    raw_original.strip()
                    if isinstance(raw_original, str)
                    else None
                )
                raw_corrected = entry.get("corrected_term")
                corrected_term = (
                    raw_corrected.strip()
                    if isinstance(raw_corrected, str)
                    else None
                )
                if not original_term or not corrected_term:
                    logger.warning(
                        "AnchorManager: skipping spelling_corrections entry with "
                        "empty original_term/corrected_term (run_id=%s, "
                        "target_kind=%s)",
                        run_id,
                        target_kind,
                    )
                    continue
                if original_term == corrected_term:
                    logger.warning(
                        "AnchorManager: skipping spelling_corrections no-op entry "
                        "(original_term == corrected_term=%r, run_id=%s)",
                        original_term,
                        run_id,
                    )
                    continue

                if target_kind == "factual_anchor":
                    spelling_anchor_id = corrected_text_to_anchor_id.get(corrected_text)
                else:  # "executive_summary"
                    spelling_anchor_id = bullet_text_to_anchor_id.get(corrected_text)
                if spelling_anchor_id is None:
                    logger.warning(
                        "AnchorManager: skipping spelling_corrections entry whose "
                        "corrected_anchor_text did not match any inserted "
                        "%s row (orphan audit row guard) (run_id=%s, "
                        "corrected_anchor_text=%r)",
                        target_kind,
                        run_id,
                        corrected_text,
                    )
                    continue

                raw_spell_note = entry.get("audit_note")
                spell_note = (
                    raw_spell_note.strip()
                    if isinstance(raw_spell_note, str) and raw_spell_note.strip()
                    else None
                )

                self.database.cursor.execute(
                    spelling_corrections_insert_sql,
                    (
                        youtube_id,
                        run_id,
                        spelling_anchor_id,
                        target_kind,
                        original_term,
                        corrected_term,
                        spell_note,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                spelling_inserted += 1
                rows_inserted += 1

            audit_total = sum(audit_counts.values())
            self.database.conn.commit()
            logger.info(
                "AnchorManager: inserted %d anchor row(s), %d fact-check audit "
                "row(s) (removed=%d corrected=%d added=%d unresolved=%d "
                "rejected_anchor=%d rejected_audit=%d), and %d "
                "spelling-correction row(s) for youtube_id=%s run_id=%s",
                rows_inserted - audit_total - spelling_inserted,
                audit_total,
                audit_counts["removed"],
                audit_counts["corrected"],
                audit_counts["added"],
                audit_counts["unresolved"],
                audit_counts[REJECTED_ANCHOR_KIND],
                audit_counts[REJECTED_AUDIT_KIND],
                spelling_inserted,
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
