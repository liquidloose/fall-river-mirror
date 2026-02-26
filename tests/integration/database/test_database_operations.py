"""
Integration tests for database operations.
"""

import pytest
from app.data.create_database import Database


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest.fixture
    def temp_database(self):
        """Create an in-memory database for testing (no temp files)."""
        db = Database(":memory:")
        yield db
        if db.is_connected:
            db.close()

    def test_database_initialization(self, temp_database):
        """Test database initialization and table creation."""
        db = temp_database

        # Database should be connected
        assert db.is_connected is True

        # Check if tables exist
        cursor = db.cursor
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "transcripts",
            "articles",
            "journalists",
            "tones",
            "categories",
            "video_queue",
            "art",
        ]
        for table in expected_tables:
            assert table in tables

    def test_transcript_crud_operations(self, temp_database):
        """Test CRUD operations for transcripts (current schema)."""
        db = temp_database
        cursor = db.cursor

        # Current transcripts columns: committee, youtube_id, content, meeting_date,
        # yt_published_date, fetch_date, model, video_title, ...
        cursor.execute(
            """
            INSERT INTO transcripts (
                committee, youtube_id, content, meeting_date, video_title
            )
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "City Council",
                "yt-test-001",
                "Test content",
                "2025-09-11",
                "Test Meeting",
            ),
        )
        db.conn.commit()

        cursor.execute(
            "SELECT * FROM transcripts WHERE video_title = ?", ("Test Meeting",)
        )
        result = cursor.fetchone()
        assert result is not None
        # id=0, committee=1, youtube_id=2, content=3, meeting_date=4, ...
        assert result[1] == "City Council"
        assert result[2] == "yt-test-001"
        assert result[3] == "Test content"
        assert result[4] == "2025-09-11"

        # UPDATE
        cursor.execute(
            "UPDATE transcripts SET content = ? WHERE video_title = ?",
            ("Updated content", "Test Meeting"),
        )
        db.conn.commit()
        cursor.execute(
            "SELECT content FROM transcripts WHERE video_title = ?",
            ("Test Meeting",),
        )
        assert cursor.fetchone()[0] == "Updated content"

        # DELETE
        cursor.execute(
            "DELETE FROM transcripts WHERE video_title = ?", ("Test Meeting",)
        )
        db.conn.commit()
        cursor.execute(
            "SELECT * FROM transcripts WHERE video_title = ?", ("Test Meeting",)
        )
        assert cursor.fetchone() is None

    def test_database_connection_management(self, temp_database):
        """Test database connection management."""
        db = temp_database

        # Should be connected initially
        assert db.is_connected is True

        # Close connection
        db.close()
        assert db.is_connected is False

        # Reconnect
        db._connect()
        assert db.is_connected is True

    def test_concurrent_operations(self, temp_database):
        """Test concurrent database operations (current schema)."""
        db = temp_database
        cursor = db.cursor

        test_data = [
            ("City Council", "yt-1", "Content 1", "2025-09-11", "Meeting 1"),
            ("Planning Board", "yt-2", "Content 2", "2025-09-12", "Meeting 2"),
            ("Board of Health", "yt-3", "Content 3", "2025-09-13", "Meeting 3"),
        ]
        for committee, yt_id, content, meeting_date, video_title in test_data:
            cursor.execute(
                """
                INSERT INTO transcripts (
                    committee, youtube_id, content, meeting_date, video_title
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (committee, yt_id, content, meeting_date, video_title),
            )
        db.conn.commit()

        cursor.execute("SELECT COUNT(*) FROM transcripts")
        assert cursor.fetchone()[0] == len(test_data)

        cursor.execute(
            "SELECT committee, video_title FROM transcripts ORDER BY meeting_date"
        )
        results = cursor.fetchall()
        assert len(results) == 3
        assert results[0][1] == "Meeting 1"
        assert results[1][1] == "Meeting 2"
        assert results[2][1] == "Meeting 3"
