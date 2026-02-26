"""
Pytest configuration and fixtures for the entire test suite.
"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_app_deps, AppDeps
from app.data.create_database import Database


@pytest.fixture(scope="session")
def test_database():
    """Create an in-memory test database for the entire test session (no temp files)."""
    test_db = Database(":memory:")
    yield test_db
    if test_db.is_connected:
        test_db.close()


@pytest.fixture
def mock_transcript_manager():
    """Mock TranscriptManager for use in overridden deps. Configure in tests via .return_value / .side_effect."""
    return Mock()


@pytest.fixture
def mock_article_generator():
    """Mock ArticleGenerator for use in overridden deps."""
    return Mock()


@pytest.fixture
def test_articles_db():
    """Mutable dict used as deps.articles_db so tests can pre-populate for GET /articles/{id}."""
    return {}


def _make_test_deps(test_db, mock_tm, mock_ag, articles_db):
    """Build AppDeps with real test DB and provided mocks/dicts."""
    return AppDeps(
        database=test_db,
        transcript_manager=mock_tm,
        article_generator=mock_ag,
        articles_db=articles_db,
        journalist_manager=None,
    )


@pytest.fixture
def client(test_database, mock_transcript_manager, mock_article_generator, test_articles_db):
    """Create a FastAPI test client with dependency overrides (test DB + mocks)."""
    def get_test_deps():
        return _make_test_deps(
            test_database,
            mock_transcript_manager,
            mock_article_generator,
            test_articles_db,
        )

    app.dependency_overrides[get_app_deps] = get_test_deps
    try:
        with TestClient(
            app, raise_server_exceptions=False
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


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
