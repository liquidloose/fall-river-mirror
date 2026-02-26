"""
Integration tests for transcript-related API endpoints.
Uses dependency overrides: client gets test DB + mocks (e.g. mock_transcript_manager).
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Integration tests for health check."""

    def test_health_check(self, client: TestClient):
        """Health check returns 200 and status ok."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "database" in data


class TestTranscriptEndpoints:
    """Integration tests for transcript API endpoints."""

    def test_get_transcript_success(
        self, client: TestClient, mock_transcript_manager
    ):
        """Successful transcript retrieval via overridden deps."""
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
        """Transcript not found returns error status."""
        mock_transcript_manager.get_transcript.side_effect = Exception(
            "Video not found"
        )
        response = client.get("/transcript/fetch/INVALID123")
        assert response.status_code in [404, 500]

    def test_get_transcript_missing_path_param(self, client: TestClient):
        """Missing youtube_id in path yields 404."""
        response = client.get("/transcript/fetch/")
        assert response.status_code == 404


class TestArticleEndpoints:
    """Integration tests for article endpoints (GET /articles/{id})."""

    def test_get_article_success(
        self, client: TestClient, test_articles_db
    ):
        """Return article when id exists in deps.articles_db."""
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
        """Return 404 when article id not in deps.articles_db."""
        response = client.get("/articles/nonexistent-id")
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()
