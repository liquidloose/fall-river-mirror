"""
Unit tests for the TranscriptManager class.

TranscriptManager is not modified; tests use mocks for the database and
YouTube API so behavior can be asserted in isolation. Caching, cache checks,
YouTube fetch, and Whisper fallback are covered. API: ``__init__(database=None)``.
"""

import pytest
from unittest.mock import Mock, patch
from app.data.transcript_manager import TranscriptManager
from app.data.enum_classes import AIAgent


class TestTranscriptManager:
    """
    TranscriptManager initialization, caching, and fetch behavior.

    Fixtures provide a mock database with the methods and attributes
    the manager uses (e.g. transcript_exists_by_youtube_id, test_write_permissions).
    """

    @pytest.fixture
    def mock_database(self):
        """Mock Database with cursor, conn, db_path, and methods used by TranscriptManager."""
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
        """_cache_transcript calls the DB cursor with youtube_id, content, and video_metadata; execute is invoked."""
        mock_cursor = mock_database.cursor
        mock_cursor.fetchone.return_value = (1,)  # table-exists check
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
        """_is_transcript_cached returns True when transcript_exists_by_youtube_id returns True."""
        mock_database.transcript_exists_by_youtube_id.return_value = True
        result = transcript_manager._is_transcript_cached("TEST123")
        assert result is True
        mock_database.transcript_exists_by_youtube_id.assert_called_once_with(
            "TEST123"
        )

    def test_is_transcript_cached_false(self, transcript_manager, mock_database):
        """_is_transcript_cached returns False when transcript_exists_by_youtube_id returns False."""
        mock_database.transcript_exists_by_youtube_id.return_value = False
        result = transcript_manager._is_transcript_cached("TEST123")
        assert result is False
        mock_database.transcript_exists_by_youtube_id.assert_called_once_with(
            "TEST123"
        )

    @patch("app.data.transcript_manager.YouTubeTranscriptApi")
    def test_fetch_from_youtube_success(self, mock_youtube_api, transcript_manager):
        """_fetch_from_youtube returns a dict with transcript, video_metadata, and source when API returns snippets."""
        # TranscriptManager uses: list(id) -> find_manually_created_transcript -> fetch() -> .snippets
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
        """When the YouTube API raises VideoUnavailable, _fetch_from_youtube uses _fetch_via_whisper and returns its transcript."""
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
        """_can_cache returns True when database is set and test_write_permissions returns True."""
        result = transcript_manager._can_cache()
        assert result is True

    def test_can_cache_without_database(self):
        """_can_cache returns False when database is None."""
        tm = TranscriptManager(database=None)
        result = tm._can_cache()
        assert result is False
