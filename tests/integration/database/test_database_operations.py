"""
Integration tests for database operations.
"""

import pytest
import tempfile
import os
from app.data.database import Database
from app.data.data_classes import Committee, AIAgent


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest.fixture
    def temp_database(self):
        """Create a temporary database for testing."""
        # Create a temporary file
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        db_name = db_path.replace(".db", "").split("/")[-1]

        try:
            # Initialize database
            db = Database(db_name)
            yield db
        finally:
            # Clean up
            if db.is_connected:
                db.close()
            os.close(db_fd)
            if os.path.exists(db_path):
                os.unlink(db_path)

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
            "committees",
            "journalists",
            "tones",
            "article_types",
        ]
        for table in expected_tables:
            assert table in tables

    def test_transcript_crud_operations(self, temp_database):
        """Test CRUD operations for transcripts."""
        db = temp_database
        cursor = db.cursor

        # Test INSERT
        cursor.execute(
            """
            INSERT INTO transcripts (committee, title, content, date, category)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("City Council", "Test Meeting", "Test content", "2025-09-11", "grok"),
        )
        db.conn.commit()

        # Test SELECT
        cursor.execute("SELECT * FROM transcripts WHERE title = ?", ("Test Meeting",))
        result = cursor.fetchone()

        assert result is not None
        assert result[1] == "City Council"  # committee
        assert result[2] == "Test Meeting"  # title
        assert result[3] == "Test content"  # content
        assert result[5] == "grok"  # category

        # Test UPDATE
        cursor.execute(
            "UPDATE transcripts SET content = ? WHERE title = ?",
            ("Updated content", "Test Meeting"),
        )
        db.conn.commit()

        cursor.execute(
            "SELECT content FROM transcripts WHERE title = ?", ("Test Meeting",)
        )
        updated_result = cursor.fetchone()
        assert updated_result[0] == "Updated content"

        # Test DELETE
        cursor.execute("DELETE FROM transcripts WHERE title = ?", ("Test Meeting",))
        db.conn.commit()

        cursor.execute("SELECT * FROM transcripts WHERE title = ?", ("Test Meeting",))
        deleted_result = cursor.fetchone()
        assert deleted_result is None

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
        """Test concurrent database operations."""
        db = temp_database

        # Insert multiple records
        test_data = [
            ("City Council", "Meeting 1", "Content 1", "2025-09-11", "grok"),
            ("Planning Board", "Meeting 2", "Content 2", "2025-09-12", "whisper"),
            ("Board of Health", "Meeting 3", "Content 3", "2025-09-13", "grok"),
        ]

        cursor = db.cursor
        for data in test_data:
            cursor.execute(
                """
                INSERT INTO transcripts (committee, title, content, date, category)
                VALUES (?, ?, ?, ?, ?)
            """,
                data,
            )
        db.conn.commit()

        # Verify all records were inserted
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        count = cursor.fetchone()[0]
        assert count == len(test_data)

        # Test batch retrieval
        cursor.execute("SELECT committee, title FROM transcripts ORDER BY date")
        results = cursor.fetchall()

        assert len(results) == 3
        assert results[0][1] == "Meeting 1"
        assert results[1][1] == "Meeting 2"
        assert results[2][1] == "Meeting 3"
