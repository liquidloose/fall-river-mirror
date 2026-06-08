"""Unit tests for Skip Whisper transcript-fetch behavior."""

from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse

from app.data.create_database import Database
from app.services.pipeline_service import PipelineService


class StubTranscriptManager:
    """Returns scripted transcript fetch outcomes per youtube_id."""

    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def get_transcript(self, youtube_id: str, allow_whisper_fallback: bool = True):
        self.calls.append(youtube_id)
        outcome = self.outcomes[youtube_id]
        if isinstance(outcome, Exception):
            return JSONResponse(
                status_code=500,
                content={"error": str(outcome)},
            )
        return outcome


@pytest.fixture
def temp_database():
    db = Database(":memory:")
    yield db
    if db.is_connected:
        db.close()


def _queue_video(db: Database, youtube_id: str, transcript_available: int) -> None:
    db.cursor.execute(
        "INSERT INTO video_queue (youtube_id, transcript_available) VALUES (?, ?)",
        (youtube_id, transcript_available),
    )
    db.conn.commit()


@pytest.mark.asyncio
async def test_skip_whisper_moves_on_after_whisper_required_failure(temp_database):
    """Skip Whisper skips a Whisper-only video and fetches the next caption-eligible one."""
    db = temp_database
    _queue_video(db, "whisper-only", 1)
    _queue_video(db, "caption-ok", 1)

    transcript_mgr = StubTranscriptManager(
        {
            "whisper-only": Exception(
                "Failed to get transcript from YouTube: whisper-only and "
                "Whisper fallback disabled for video whisper-only; raising without retry"
            ),
            "caption-ok": {
                "source": "database_cache",
                "transcript": '{"snippets": []}',
                "content": "hello",
            },
        }
    )
    service = PipelineService(db, transcript_mgr, None, None)

    with patch("app.services.pipeline_service.time.sleep"):
        result = await service.run_bulk_fetch_transcripts(
            amount=1,
            auto_build=False,
            include_whisper_items=False,
        )

    assert result["success"] is True
    assert result["transcripts_fetched"] == 1
    assert result["skipped_whisper"] == 1
    statuses = {row["youtube_id"]: row["status"] for row in result["results"]}
    assert statuses["whisper-only"] == "skipped_requires_whisper"
    assert statuses["caption-ok"] == "success"

    db.cursor.execute("SELECT transcript_available FROM video_queue WHERE youtube_id = ?", ("whisper-only",))
    assert db.cursor.fetchone()[0] == 0
    db.cursor.execute("SELECT youtube_id FROM video_queue")
    assert db.cursor.fetchall() == []


@pytest.mark.asyncio
async def test_skip_whisper_skips_transcript_available_zero_without_fetch(temp_database):
    """Skip Whisper walks past queue rows already marked Whisper-required."""
    db = temp_database
    _queue_video(db, "needs-whisper", 0)
    _queue_video(db, "caption-ok", 1)

    transcript_mgr = StubTranscriptManager(
        {
            "caption-ok": {
                "source": "database_cache",
                "transcript": '{"snippets": []}',
                "content": "hello",
            },
        }
    )
    service = PipelineService(db, transcript_mgr, None, None)

    with patch("app.services.pipeline_service.time.sleep"):
        result = await service.run_bulk_fetch_transcripts(
            amount=1,
            auto_build=False,
            include_whisper_items=False,
        )

    assert result["success"] is True
    assert result["transcripts_fetched"] == 1
    assert result["skipped_whisper"] == 1
    assert transcript_mgr.calls == ["caption-ok"]
    assert result["results"][0]["status"] == "skipped_requires_whisper"
    assert result["results"][0]["youtube_id"] == "needs-whisper"
