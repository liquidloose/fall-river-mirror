"""
Unit tests for TranscriptManager class.
Adjusted to current TranscriptManager API: __init__(database=None), no committee arg.
"""

import pytest
from unittest.mock import Mock, patch
from app.data.transcript_manager import TranscriptManager
from app.data.enum_classes import AIAgent


class TestTranscriptManager:
    """Test cases for TranscriptManager class."""

    @pytest.fixture
    def mock_database(self):
        """Mock database for testing (matches current Database usage)."""
        mock_db = Mock()
        mock_db.cursor = Mock()
        mock_db.conn = Mock()
        mock_db.db_path = "/tmp/test.db"
        mock_db.is_connected = True
        mock_db.test_write_permissions = Mock(return_value=True)
        mock_db.transcript_exists_by_youtube_id = Mock(return_value=False)
        return mock_db

    @pytest.fixture
    def transcript_manager(self, mock_database):
        """Create a TranscriptManager instance with mock database."""
        return TranscriptManager(database=mock_database)

    def test_init(self, mock_database):
        """Test TranscriptManager initialization (current API: database only)."""
        tm = TranscriptManager(database=mock_database)
        assert tm.database == mock_database
        assert tm.category == AIAgent.GROK

    def test_cache_transcript_success(
        self, transcript_manager, mock_database, mock_transcript_data
    ):
        """Test successful transcript caching (current _cache_transcript signature)."""
        mock_cursor = mock_database.cursor
        mock_cursor.fetchone.return_value = (1,)  # table exists
        video_metadata = {
            "title": "Test Meeting",
            "published_at": None,
            "committee": mock_transcript_data["committee"],
            "duration_seconds": None,
            "duration_formatted": "",
            "channel_title": None,
            "meeting_date": None,
            "view_count": None,
            "like_count": None,
            "comment_count": None,
        }

        transcript_manager._cache_transcript(
            youtube_id=mock_transcript_data["video_id"],
            content=mock_transcript_data["content"],
            video_metadata=video_metadata,
            committee=mock_transcript_data["committee"],
        )

        assert mock_cursor.execute.call_count >= 1

    def test_is_transcript_cached_true(self, transcript_manager, mock_database):
        """Test transcript cache check when transcript exists."""
        mock_database.transcript_exists_by_youtube_id.return_value = True
        result = transcript_manager._is_transcript_cached("TEST123")
        assert result is True
        mock_database.transcript_exists_by_youtube_id.assert_called_once_with(
            "TEST123"
        )

    def test_is_transcript_cached_false(self, transcript_manager, mock_database):
        """Test transcript cache check when transcript doesn't exist."""
        mock_database.transcript_exists_by_youtube_id.return_value = False
        result = transcript_manager._is_transcript_cached("TEST123")
        assert result is False
        mock_database.transcript_exists_by_youtube_id.assert_called_once_with(
            "TEST123"
        )

    @patch("app.data.transcript_manager.YouTubeTranscriptApi")
    def test_fetch_from_youtube_success(self, mock_youtube_api, transcript_manager):
        """Test successful YouTube transcript fetching (returns rich dict)."""
        # API chain: list(id) -> find_manually_created_transcript -> fetch() -> .snippets
        mock_snippet = Mock()
        mock_snippet.text = "Mocked transcript content"
        mock_snippet.start = 0.0
        mock_snippet.duration = 1.0
        mock_fetched = Mock()
        mock_fetched.snippets = [mock_snippet]
        mock_transcript = Mock()
        mock_transcript.fetch.return_value = mock_fetched
        mock_list_obj = Mock()
        mock_list_obj.find_manually_created_transcript.return_value = mock_transcript
        mock_api_instance = Mock()
        mock_api_instance.list.return_value = mock_list_obj
        mock_youtube_api.return_value = mock_api_instance

        result = transcript_manager._fetch_from_youtube("TEST123")

        assert "transcript" in result
        assert "video_metadata" in result
        assert result["source"] == "youtube_transcript_api"

    @patch("app.data.transcript_manager.YouTubeTranscriptApi")
    @patch.object(TranscriptManager, "_fetch_via_whisper")
    def test_fetch_from_youtube_fallback_to_whisper(
        self, mock_whisper, mock_youtube_api, transcript_manager
    ):
        """Test fallback to Whisper when YouTube API fails."""
        from youtube_transcript_api._errors import VideoUnavailable

        mock_list_obj = Mock()
        mock_list_obj.find_manually_created_transcript.side_effect = VideoUnavailable(
            "TEST123"
        )
        mock_list_obj.find_generated_transcript.side_effect = VideoUnavailable(
            "TEST123"
        )
        mock_api_instance = Mock()
        mock_api_instance.list.return_value = mock_list_obj
        mock_youtube_api.return_value = mock_api_instance
        mock_whisper.return_value = "Whisper transcript content"

        result = transcript_manager._fetch_from_youtube("TEST123")

        assert "transcript" in result
        assert result["transcript"] == "Whisper transcript content"
        mock_whisper.assert_called_once_with("TEST123")

    def test_can_cache_with_database(self, transcript_manager):
        """Test cache availability when database is present and writable."""
        result = transcript_manager._can_cache()
        assert result is True

    def test_can_cache_without_database(self):
        """Test cache availability when database is None."""
        tm = TranscriptManager(database=None)
        result = tm._can_cache()
        assert result is False
