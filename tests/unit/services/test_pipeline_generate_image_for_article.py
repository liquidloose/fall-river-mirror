"""Unit tests for single-article image generation in PipelineService."""

from unittest.mock import MagicMock, patch

import pytest

from app.data.enum_classes import Artist, ImageModel
from app.services.pipeline_service import PipelineService


def _pipeline_service(db, image_svc):
    return PipelineService(
        database=db,
        transcript_manager=MagicMock(),
        journalist_manager=MagicMock(),
        image_service=image_svc,
    )


def test_generate_image_for_article_skips_when_art_exists():
    db = MagicMock()
    db.get_article_by_id.return_value = {
        "id": 5,
        "title": "Title",
        "bullet_points": "<ul><li>a</li></ul>",
        "transcript_id": 1,
        "youtube_id": "yt-5",
    }
    db.cursor.fetchone.return_value = (99,)

    svc = _pipeline_service(db, MagicMock())
    result = svc.generate_image_for_article(5, Artist.FRA1, ImageModel.GPT_IMAGE_1)

    assert result["success"] is True
    assert result["skipped"] is True


def test_generate_image_for_article_success():
    db = MagicMock()
    db.get_article_by_id.return_value = {
        "id": 5,
        "title": "Title",
        "bullet_points": "<ul><li>a</li></ul>",
        "transcript_id": 1,
        "youtube_id": "yt-5",
    }
    db.cursor.fetchone.return_value = None
    db.add_art.return_value = 77

    image_svc = MagicMock()
    image_svc.decode_url.return_value = b"\x89PNG\r\n\x1a\nbytes"

    svc = _pipeline_service(db, image_svc)
    mock_artist = MagicMock()
    mock_artist.generate_image.return_value = {
        "image_url": "https://example.com/img.png",
        "prompt_used": "prompt",
        "artist": "FRA1",
    }

    with patch.object(svc, "generate_image_for_article", wraps=svc.generate_image_for_article):
        with patch(
            "app.services.pipeline_service.FRA1",
            return_value=mock_artist,
        ):
            result = svc.generate_image_for_article(5, Artist.FRA1, ImageModel.GPT_IMAGE_1)

    assert result["success"] is True
    assert result["art_id"] == 77
    db.add_art.assert_called_once()


def test_generate_image_for_article_fails_without_bullets():
    db = MagicMock()
    db.get_article_by_id.return_value = {
        "id": 5,
        "title": "Title",
        "bullet_points": "",
        "transcript_id": 1,
    }
    db.cursor.fetchone.return_value = None

    svc = _pipeline_service(db, MagicMock())
    result = svc.generate_image_for_article(5, Artist.FRA1, ImageModel.GPT_IMAGE_1)

    assert result["success"] is False
    assert "bullet_points" in result["error"]
