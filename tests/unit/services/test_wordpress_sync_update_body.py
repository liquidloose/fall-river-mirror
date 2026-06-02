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
    }
    return db


def test_update_article_body_payload_has_no_title(mock_db):
    svc = WordPressSyncService(mock_db, base_url="https://wp.example")
    captured: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success": true}'
    mock_response.json.return_value = {"success": True, "post_id": 123}

    def capture_post(*_args, **kwargs):
        captured.update(kwargs)
        return mock_response

    with patch("app.services.wordpress_sync_service.requests.post", side_effect=capture_post):
        with patch.object(svc, "_request_with_jwt_retry", side_effect=lambda fn: fn()):
            result = svc.update_article_body_on_wordpress("abc123")

    assert result["success"] is True
    payload = captured["json"]
    assert "title" not in payload
    assert "article_id" not in payload
    assert payload == {
        "youtube_id": "abc123",
        "content": "<p>body</p>",
        "bullet_points": "<ul><li>one</li></ul>",
    }


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

    with patch("app.services.wordpress_sync_service.requests.post", side_effect=capture_post):
        with patch.object(svc, "_request_with_jwt_retry", side_effect=lambda fn: fn()):
            svc.update_article_body_on_wordpress("abc123")

    assert posted_url == [f"https://wp.example{DEFAULT_API_PATH_UPDATE_BODY}"]
