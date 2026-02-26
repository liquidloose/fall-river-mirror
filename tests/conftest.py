"""
Pytest configuration and shared fixtures for the test suite.

This module wires the app for testing by overriding FastAPI's dependency injection.
Routes that use ``Depends(get_app_deps)`` receive a test double (real in-memory DB +
mocks for externals) instead of production dependencies, so tests run without
hitting YouTube, WordPress, or the real database.
"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_app_deps, AppDeps
from app.data.create_database import Database


@pytest.fixture(scope="session")
def test_database():
    """
    Session-scoped in-memory SQLite database.

    Uses ``Database(":memory:")`` so no temp files are created. Shared across
    all tests that need a DB; schema is created once. Safe because tests do
    not rely on shared state in the DB.
    """
    test_db = Database(":memory:")
    yield test_db
    if test_db.is_connected:
        test_db.close()


@pytest.fixture
def mock_transcript_manager():
    """
    Mock for ``TranscriptManager`` used in overridden ``AppDeps``.

    In tests, set ``mock_transcript_manager.get_transcript.return_value = {...}``
    or ``.side_effect = Exception(...)`` to drive success or error behavior
    for transcript endpoints.
    """
    return Mock()


@pytest.fixture
def mock_article_generator():
    """
    Mock for ``ArticleGenerator`` in overridden ``AppDeps``.

    Used by the test client's dependency override; configure in tests if
    an endpoint under test calls the article generator.
    """
    return Mock()


@pytest.fixture
def test_articles_db():
    """
    Mutable dict used as ``deps.articles_db`` for GET /articles/{id} tests.

    Pre-populate in a test (e.g. ``test_articles_db["art-1"] = {"title": "..."}``)
    to assert the endpoint returns that data. Same dict is reused for the
    duration of the test.
    """
    return {}


def _make_test_deps(test_db, mock_tm, mock_ag, articles_db):
    """
    Build an ``AppDeps`` instance for the test client.

    Uses a real in-memory DB and the fixture mocks/dicts so API tests
    exercise real SQL without external services.
    """
    return AppDeps(
        database=test_db,
        transcript_manager=mock_tm,
        article_generator=mock_ag,
        articles_db=articles_db,
        journalist_manager=None,
    )


@pytest.fixture
def client(test_database, mock_transcript_manager, mock_article_generator, test_articles_db):
    """
    FastAPI test client with dependency overrides applied.

    When a request hits a route that uses ``Depends(get_app_deps)``, FastAPI
    calls our override and injects test deps (session DB + mocks). Overrides
    are cleared in a ``finally`` so the real app is unchanged after the test.
    ``raise_server_exceptions=False`` so 500 responses return a response
    object instead of raising, allowing tests to assert on error status.
    """
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
    """
    Sample transcript payload for unit tests (e.g. ``_cache_transcript``).

    Used by tests that need a consistent video_id, committee, and content
    without hitting the real transcript API.
    """
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
    """
    Sample article request payload for tests that call article-generation endpoints.

    Fields match the shape expected by the API (context, prompt, article_type, etc.).
    """
    return {
        "context": "Test context for article generation",
        "prompt": "Write a summary of the meeting",
        "article_type": "summary",
        "tone": "professional",
        "committee": "city_council",
    }
