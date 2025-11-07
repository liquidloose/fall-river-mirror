"""
Integration tests for transcript-related API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


class TestTranscriptEndpoints:
    """Integration tests for transcript API endpoints."""

    def test_health_check(self, client: TestClient):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()

    @patch("app.main.TranscriptManager")
    def test_get_transcript_success(self, mock_transcript_manager, client: TestClient):
        """Test successful transcript retrieval."""
        # Mock the transcript manager
        mock_tm_instance = Mock()
        mock_transcript_manager.return_value = mock_tm_instance
        mock_tm_instance.get_transcript.return_value = {
            "transcript": "Test transcript content",
            "source": "youtube",
            "video_id": "TEST123",
        }

        response = client.get("/transcript/TEST123")

        # Should return success with transcript data
        assert response.status_code == 200
        data = response.json()
        assert "transcript" in data
        assert data["video_id"] == "TEST123"

    @patch("app.main.TranscriptManager")
    def test_get_transcript_not_found(
        self, mock_transcript_manager, client: TestClient
    ):
        """Test transcript retrieval when video not found."""
        # Mock the transcript manager to return error
        mock_tm_instance = Mock()
        mock_transcript_manager.return_value = mock_tm_instance
        mock_tm_instance.get_transcript.side_effect = Exception("Video not found")

        response = client.get("/transcript/INVALID123")

        # Should return error
        assert response.status_code in [404, 500]

    def test_get_transcript_invalid_video_id(self, client: TestClient):
        """Test transcript retrieval with invalid video ID format."""
        response = client.get("/transcript/")

        # Should return 404 for missing video ID
        assert response.status_code == 404


class TestArticleEndpoints:
    """Integration tests for article generation endpoints."""

    @patch("app.main.ArticleGenerator")
    def test_generate_article_success(
        self, mock_article_generator, client: TestClient, mock_article_data
    ):
        """Test successful article generation."""
        # Mock the article generator
        mock_ag_instance = Mock()
        mock_article_generator.return_value = mock_ag_instance
        mock_ag_instance.generate_article.return_value = {
            "article": "Generated article content",
            "title": "Test Article",
            "author": "AI Journalist",
        }

        response = client.post("/articles/generate", json=mock_article_data)

        assert response.status_code == 200
        data = response.json()
        assert "article" in data
        assert "title" in data

    def test_generate_article_invalid_data(self, client: TestClient):
        """Test article generation with invalid request data."""
        invalid_data = {
            "context": "",  # Empty context should fail validation
            "prompt": "Test prompt",
            # Missing required fields
        }

        response = client.post("/articles/generate", json=invalid_data)

        # Should return validation error
        assert response.status_code == 422
