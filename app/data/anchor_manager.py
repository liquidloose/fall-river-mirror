"""
Persistence for anchor rows — the RAG-ready chunks emitted by extractors
(e.g. Gemma Nye) into the ``anchors`` table.

Two row types share the same schema and live in the same table, distinguished
by ``doc_type``:

- ``factual_anchor``: one row per ``factual_anchor_items[i]`` in the envelope.
  Carries timestamp + headline + ``has_official_vote`` / ``has_official_roll_call``.
- ``executive_summary``: one row per ``executive_summary_bullets[i]`` string.
  Timestamps and headline are NULL; the bullet text fills both ``anchor_text``
  and ``text_to_embed``; vote flags default to 0.

A single extractor invocation writes N anchor rows that all share the same
``run_id`` UUID, so the rows are coherent across the table. Re-extracting the
same transcript later produces a new ``run_id`` and a new set of rows; both
runs coexist (no overwrite).

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
                                "has_official_roll_call": false,
                                "text_to_embed": "..."
                            }
                        ]
                    }

                Missing keys are treated as empty lists. Per-item fields
                read defensively: ``anchor_text`` and ``text_to_embed`` are
                required on factual anchors; everything else falls back to
                NULL / 0.
            extractor_name: Name string (e.g. ``"Gemma Nye"``) written to
                every row's ``extractor_name`` column for provenance.
            model: Provider model id (e.g. ``"gemini-2.0-pro"``); written to
                every row's ``model`` column. May be ``None``.

        Returns:
            Total number of rows inserted (factual anchors + summary bullets).

        Raises:
            Exception: Any DB error during the insert batch triggers a full
                rollback and re-raises. Callers see the original SQLite
                exception so they can log / surface it.
        """
        bullets: List[str] = list(envelope.get("executive_summary_bullets") or [])
        anchors: List[Dict[str, Any]] = list(envelope.get("factual_anchor_items") or [])
        created_at = datetime.now(timezone.utc).isoformat()
        rows_inserted = 0

        insert_sql = """
            INSERT INTO anchors (
                youtube_id, run_id, doc_type,
                timestamp_string, timestamp_seconds, anchor_headline,
                anchor_text, has_official_vote, has_official_roll_call,
                text_to_embed, extractor_name, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

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
                        1 if anchor.get("has_official_roll_call") else 0,
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
                        0,
                        bullet_text,
                        extractor_name,
                        model,
                        created_at,
                    ),
                )
                rows_inserted += 1

            self.database.conn.commit()
            logger.info(
                "AnchorManager: inserted %d anchor row(s) for youtube_id=%s run_id=%s",
                rows_inserted,
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
