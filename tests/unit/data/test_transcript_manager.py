"""
Unit tests for TranscriptManager class.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.data.transcript_manager import TranscriptManager
from app.data.data_classes import AIAgent, Committee


class TestTranscriptManager:
    """Test cases for TranscriptManager class."""

    @pytest.fixture
    def mock_database(self):
        """Mock database for testing."""
        mock_db = Mock()
        mock_db.cursor = Mock()
        mock_db.is_connected = True
        return mock_db

    @pytest.fixture
    def transcript_manager(self, mock_database):
        """Create a TranscriptManager instance with mock database."""
        return TranscriptManager(committee="Test Committee", database=mock_database)

    def test_init(self, mock_database):
        """Test TranscriptManager initialization."""
        tm = TranscriptManager(committee="Test Committee", database=mock_database)
        assert tm.committee == "Test Committee"
        assert tm.database == mock_database

    @patch("app.data.transcript_manager.sqlite3.connect")
    def test_cache_transcript_success(
        self, mock_connect, transcript_manager, mock_transcript_data
    ):
        """Test successful transcript caching."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock successful insert
        mock_cursor.fetchone.return_value = (1,)  # Mock insert ID

        # Test the method
        transcript_manager._cache_transcript(
            video_id=mock_transcript_data["video_id"],
            transcript=mock_transcript_data["content"],
            committee=mock_transcript_data["committee"],
        )

        # Verify database operations were called
        mock_connect.assert_called()
        mock_cursor.execute.assert_called()
        mock_conn.commit.assert_called()

    def test_is_transcript_cached_true(self, transcript_manager):
        """Test transcript cache check when transcript exists."""
        # Mock database cursor to return a result
        transcript_manager.database.cursor.fetchone.return_value = (1, "test_content")

        result = transcript_manager._is_transcript_cached("TEST123")

        assert result is True
        transcript_manager.database.cursor.execute.assert_called_once()

    def test_is_transcript_cached_false(self, transcript_manager):
        """Test transcript cache check when transcript doesn't exist."""
        # Mock database cursor to return None
        transcript_manager.database.cursor.fetchone.return_value = None

        result = transcript_manager._is_transcript_cached("TEST123")

        assert result is False
        transcript_manager.database.cursor.execute.assert_called_once()

    @patch("app.data.transcript_manager.YouTubeTranscriptApi")
    def test_fetch_from_youtube_success(self, mock_youtube_api, transcript_manager):
        """Test successful YouTube transcript fetching."""
        # Mock YouTube API response
        mock_api_instance = Mock()
        mock_youtube_api.return_value = mock_api_instance
        mock_api_instance.fetch.return_value = "Mocked transcript content"

        result = transcript_manager._fetch_from_youtube("TEST123")

        assert result == "Mocked transcript content"
        mock_api_instance.fetch.assert_called_once_with("TEST123")

    @patch("app.data.transcript_manager.YouTubeTranscriptApi")
    @patch.object(TranscriptManager, "_fetch_via_whisper")
    def test_fetch_from_youtube_fallback_to_whisper(
        self, mock_whisper, mock_youtube_api, transcript_manager
    ):
        """Test fallback to Whisper when YouTube API fails."""
        # Mock YouTube API to raise exception
        mock_api_instance = Mock()
        mock_youtube_api.return_value = mock_api_instance
        mock_api_instance.fetch.side_effect = Exception("YouTube API failed")

        # Mock Whisper fallback
        mock_whisper.return_value = "Whisper transcript content"

        result = transcript_manager._fetch_from_youtube("TEST123")

        assert result == "Whisper transcript content"
        mock_whisper.assert_called_once_with("TEST123")

    def test_can_cache_with_database(self, transcript_manager):
        """Test cache availability when database is present."""
        result = transcript_manager._can_cache()
        assert result is True

    def test_can_cache_without_database(self):
        """Test cache availability when database is None."""
        tm = TranscriptManager(committee="Test", database=None)
        result = tm._can_cache()
        assert result is False
