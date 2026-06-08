"""Unit tests for WordPress body-only sync."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.wordpress_sync_service import (
    DEFAULT_API_PATH_UPDATE_BODY,
    WordPressSyncService,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_article_by_youtube_id.return_value = {
        "id": 42,
        "youtube_id": "abc123",
        "content": "<p>body</p>",
        "bullet_points": "<ul><li>one</li></ul>",
        "title": "Original Title",
        "committee": "Board of Health",
        "transcript_id": 7,
    }
    db.cursor.fetchone.side_effect = [
        ("2024-01-15",),
        (1, b"\x89PNG\r\n\x1a\nfake", "gpt-image-1"),
    ]
    return db


def test_update_article_body_payload_body_only_when_already_on_wp(mock_db):
    svc = WordPressSyncService(mock_db, base_url="https://wp.example")
    captured: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success": true}'
    mock_response.json.return_value = {"success": True, "post_id": 123}

    def capture_post(*_args, **kwargs):
        captured.update(kwargs)
        return mock_response

    with patch.object(
        svc,
        "get_article_youtube_ids_result",
        return_value={"success": True, "youtube_ids": {"abc123"}},
    ):
        with patch("app.services.wordpress_sync_service.requests.post", side_effect=capture_post):
            with patch.object(svc, "_request_with_jwt_retry", side_effect=lambda fn: fn()):
                result = svc.update_article_body_on_wordpress("abc123")

    assert result["success"] is True
    payload = captured["json"]
    assert payload == {
        "youtube_id": "abc123",
        "title": "Original Title",
        "content": "<p>body</p>",
        "bullet_points": "<ul><li>one</li></ul>",
    }


def test_update_article_body_payload_includes_create_metadata_when_not_on_wp(mock_db):
    svc = WordPressSyncService(mock_db, base_url="https://wp.example")
    captured: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success": true}'
    mock_response.json.return_value = {"success": True, "post_id": 123, "created": True}

    def capture_post(*_args, **kwargs):
        captured.update(kwargs)
        return mock_response

    with patch.object(
        svc,
        "get_article_youtube_ids_result",
        return_value={"success": True, "youtube_ids": set()},
    ):
        with patch("app.services.wordpress_sync_service.requests.post", side_effect=capture_post):
            with patch.object(svc, "_request_with_jwt_retry", side_effect=lambda fn: fn()):
                result = svc.update_article_body_on_wordpress("abc123")

    assert result["success"] is True
    payload = captured["json"]
    assert payload["youtube_id"] == "abc123"
    assert payload["committee"] == "Board of Health"
    assert payload["meeting_date"] == "2024-01-15"
    assert payload["featured_image"].startswith("data:image/png;base64,")


def test_update_article_body_requires_art_for_create_on_miss(mock_db):
    svc = WordPressSyncService(mock_db, base_url="https://wp.example")
    mock_db.cursor.fetchone.side_effect = [
        ("2024-01-15",),
        None,
    ]

    with patch.object(
        svc,
        "get_article_youtube_ids_result",
        return_value={"success": True, "youtube_ids": set()},
    ):
        result = svc.update_article_body_on_wordpress("abc123")

    assert result["success"] is False
    assert "featured_image (art) required" in result["error"]


def test_update_article_body_uses_update_body_api_path(mock_db):
    svc = WordPressSyncService(mock_db, base_url="https://wp.example")
    assert svc._api_path_update_body == DEFAULT_API_PATH_UPDATE_BODY

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"{}"
    mock_response.json.return_value = {}

    posted_url: list[str] = []

    def capture_post(url, **_kwargs):
        posted_url.append(url)
        return mock_response

    with patch.object(
        svc,
        "get_article_youtube_ids_result",
        return_value={"success": True, "youtube_ids": {"abc123"}},
    ):
        with patch("app.services.wordpress_sync_service.requests.post", side_effect=capture_post):
            with patch.object(svc, "_request_with_jwt_retry", side_effect=lambda fn: fn()):
                svc.update_article_body_on_wordpress("abc123")

    assert posted_url == [f"https://wp.example{DEFAULT_API_PATH_UPDATE_BODY}"]
