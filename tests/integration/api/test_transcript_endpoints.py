"""
Integration tests for API endpoints that use dependency overrides.

These tests hit real HTTP routes via FastAPI's TestClient. The app receives
test dependencies (in-memory DB and mocks for TranscriptManager, etc.) so
no external services or production data are used. Failures here usually
point to route wiring, request/response shape, or the test double's configuration.
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """
    Health check endpoint (GET /).

    Asserts the server responds with status and database state. Uses the
    overridden deps so the reported DB status reflects the test database.
    """

    def test_health_check(self, client: TestClient):
        """GET / returns 200 with status ok and a database field in the JSON body."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "database" in data


class TestTranscriptEndpoints:
    """
    Transcript fetch endpoint (GET /transcript/fetch/{youtube_id}).

    Behavior is driven by ``mock_transcript_manager``: set return_value for
    success or side_effect for errors. No real YouTube or DB transcript lookup.
    """

    def test_get_transcript_success(
        self, client: TestClient, mock_transcript_manager
    ):
        """When the mock returns transcript data, response is 200 and body contains transcript and video_id."""
        mock_transcript_manager.get_transcript.return_value = {
            "transcript": "Test transcript content",
            "source": "youtube",
            "video_id": "TEST123",
        }
        response = client.get("/transcript/fetch/TEST123")
        assert response.status_code == 200
        data = response.json()
        assert "transcript" in data
        assert data["video_id"] == "TEST123"

    def test_get_transcript_not_found(
        self, client: TestClient, mock_transcript_manager
    ):
        """When the mock raises, response is 404 or 500 (server exception not re-raised by client)."""
        mock_transcript_manager.get_transcript.side_effect = Exception(
            "Video not found"
        )
        response = client.get("/transcript/fetch/INVALID123")
        assert response.status_code in [404, 500]

    def test_get_transcript_missing_path_param(self, client: TestClient):
        """GET /transcript/fetch/ with no path segment returns 404."""
        response = client.get("/transcript/fetch/")
        assert response.status_code == 404


class TestArticleEndpoints:
    """
    Article retrieval endpoint (GET /articles/{article_id}).

    Data comes from the overridden ``deps.articles_db``. Use the
    ``test_articles_db`` fixture to pre-populate entries and assert
    the response body.
    """

    def test_get_article_success(
        self, client: TestClient, test_articles_db
    ):
        """When the id exists in test_articles_db, response is 200 and body matches stored article."""
        test_articles_db["art-1"] = {
            "title": "Test Article",
            "content": "Body",
        }
        response = client.get("/articles/art-1")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Article"
        assert data["content"] == "Body"

    def test_get_article_not_found(self, client: TestClient):
        """When the id is not in test_articles_db, response is 404 with a detail message."""
        response = client.get("/articles/nonexistent-id")
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()
