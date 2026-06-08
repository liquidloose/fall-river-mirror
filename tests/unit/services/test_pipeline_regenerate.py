"""Unit tests for article regeneration from anchors."""

from unittest.mock import MagicMock, patch

import pytest

from app.data.create_database import Database
from app.data.enum_classes import ArticleType, Journalist, Tone
from app.services.pipeline_service import PipelineService


@pytest.fixture
def temp_database():
    db = Database(":memory:")
    yield db
    if db.is_connected:
        db.close()


def _seed_article(db: Database, youtube_id: str, *, title: str = "Original Title") -> int:
    db.cursor.execute(
        "INSERT INTO transcripts (committee, youtube_id, content) VALUES (?, ?, ?)",
        ("test-committee", youtube_id, "transcript body"),
    )
    transcript_id = db.cursor.lastrowid
    db.cursor.execute(
        "INSERT INTO journalists (full_name, first_name, last_name) VALUES (?, ?, ?)",
        ("Test Journalist", "Test", "Journalist"),
    )
    journalist_id = db.cursor.lastrowid
    db.conn.commit()
    return db.add_article(
        committee="test-committee",
        youtube_id=youtube_id,
        journalist_id=journalist_id,
        content="old content",
        transcript_id=transcript_id,
        date="2026-01-01",
        article_type=ArticleType.SEQUENTIAL_NEWS.value,
        tone=Tone.PROFESSIONAL.value,
        title=title,
    )


def _seed_transcript_only(db: Database, youtube_id: str) -> int:
    db.cursor.execute(
        "INSERT INTO transcripts (committee, youtube_id, content) VALUES (?, ?, ?)",
        ("test-committee", youtube_id, "transcript body"),
    )
    db.conn.commit()
    return db.cursor.lastrowid


def test_regenerate_updates_content_not_title(temp_database):
    db = temp_database
    youtube_id = "vid-regen-1"
    article_id = _seed_article(db, youtube_id)

    mock_journalist = MagicMock()
    mock_journalist.generate_article.return_value = {
        "content": "<p>regenerated body</p>",
        "title": "LLM Title Must Be Ignored",
    }

    service = PipelineService(db, None, None, None)
    with patch.object(
        service, "_resolve_journalist_instance", return_value=(mock_journalist, 1)
    ):
        with patch.object(
            service, "build_article_context_from_anchors", return_value="anchor ctx"
        ):
            with patch.object(
                service, "get_latest_executive_summary_bullets", return_value=["bullet one"]
            ):
                with patch.object(service, "get_unresolved_audit_notes", return_value=[]):
                    result = service.regenerate_article_from_anchors(
                        youtube_id,
                        journalist=Journalist.FR_J1,
                        tone=Tone.PROFESSIONAL,
                        article_type=ArticleType.SEQUENTIAL_NEWS,
                    )

    assert result["success"] is True
    assert result["mode"] == "updated"
    assert result["article_id"] == article_id
    assert result["title"] == "Original Title"
    assert result["bullets_count"] == 1

    updated = db.get_article_by_id(article_id)
    assert updated is not None
    assert updated["title"] == "Original Title"
    assert "<p>regenerated body</p>" in updated["content"]
    assert "bullet one" in (updated.get("bullet_points") or "")


def test_regenerate_does_not_call_add_article(temp_database):
    db = temp_database
    youtube_id = "vid-regen-2"
    _seed_article(db, youtube_id)

    mock_journalist = MagicMock()
    mock_journalist.generate_article.return_value = {"content": "<p>new</p>", "title": "x"}

    service = PipelineService(db, None, None, None)
    with patch.object(db, "add_article") as add_article_mock:
        with patch.object(
            service, "_resolve_journalist_instance", return_value=(mock_journalist, 1)
        ):
            with patch.object(
                service, "build_article_context_from_anchors", return_value="ctx"
            ):
                with patch.object(
                    service, "get_latest_executive_summary_bullets", return_value=[]
                ):
                    with patch.object(service, "get_unresolved_audit_notes", return_value=[]):
                        service.regenerate_article_from_anchors(
                            youtube_id,
                            journalist=Journalist.FR_J1,
                            tone=Tone.PROFESSIONAL,
                            article_type=ArticleType.SEQUENTIAL_NEWS,
                        )

    add_article_mock.assert_not_called()


def test_regenerate_creates_article_when_missing(temp_database):
    db = temp_database
    youtube_id = "vid-create-1"
    transcript_id = _seed_transcript_only(db, youtube_id)

    mock_journalist = MagicMock()
    mock_journalist.generate_article.return_value = {
        "content": "<p>new article body</p>",
        "title": "Fresh LLM Title",
    }

    service = PipelineService(db, None, None, None)
    with patch.object(
        service, "_resolve_journalist_instance", return_value=(mock_journalist, 1)
    ):
        with patch.object(
            service, "build_article_context_from_anchors", return_value="anchor ctx"
        ):
            with patch.object(
                service, "get_latest_executive_summary_bullets", return_value=["bullet"]
            ):
                with patch.object(service, "get_unresolved_audit_notes", return_value=[]):
                    result = service.regenerate_article_from_anchors(
                        youtube_id,
                        journalist=Journalist.FR_J1,
                        tone=Tone.PROFESSIONAL,
                        article_type=ArticleType.SEQUENTIAL_NEWS,
                    )

    assert result["success"] is True
    assert result["mode"] == "created"
    article = db.get_article_by_youtube_id(youtube_id)
    assert article is not None
    assert result["title"] == "Fresh LLM Title"
    assert article["title"] == "Fresh LLM Title"
    assert "<p>new article body</p>" in article["content"]
    assert article["transcript_id"] == transcript_id


@pytest.mark.asyncio
async def test_bulk_extract_anchors_reports_requested_vs_found(temp_database):
    db = temp_database
    for i in range(3):
        db.cursor.execute(
            "INSERT INTO transcripts (youtube_id, content) VALUES (?, ?)",
            (f"vid-extract-{i}", f"content {i}"),
        )
    db.conn.commit()

    service = PipelineService(db, None, None, None)

    def fake_extract(youtube_id, **_kwargs):
        return {"success": True, "youtube_id": youtube_id}

    with patch.object(service, "run_extract_anchors", side_effect=fake_extract):
        result = await service.run_bulk_extract_anchors(8)

    assert result["requested"] == 8
    assert result["found_without_anchors"] == 3
    assert result["processed"] == 3
    assert result["anchors_extracted"] == 3
    assert "Requested 8" in result["message"]
    assert "found 3" in result["message"]
