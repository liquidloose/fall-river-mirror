"""
Pytest configuration and fixtures for the entire test suite.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.data.database import Database


@pytest.fixture(scope="session")
def test_database():
    """Create a temporary test database for the entire test session."""
    # Create a temporary file for the test database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    db_name = db_path.replace(".db", "").split("/")[-1]

    try:
        # Initialize test database
        test_db = Database(db_name)
        yield test_db
    finally:
        # Clean up
        if test_db.is_connected:
            test_db.close()
        os.close(db_fd)
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_transcript_data():
    """Mock transcript data for testing."""
    return {
        "video_id": "TEST123ABC",
        "committee": "City Council",
        "title": "Test Committee Meeting",
        "content": "This is a test transcript content for testing purposes.",
        "date": "2025-09-11T20:30:00",
        "category": "grok",
    }


@pytest.fixture
def mock_article_data():
    """Mock article data for testing."""
    return {
        "context": "Test context for article generation",
        "prompt": "Write a summary of the meeting",
        "article_type": "summary",
        "tone": "professional",
        "committee": "city_council",
    }
