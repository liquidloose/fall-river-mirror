"""Integration tests for POST /pipeline/regenerate/{amount}."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.data.enum_classes import Extractor, Journalist, TextModel, Tone, ArticleType
from app.dependencies import AppDependencies
from app.main import app


class RegenerateStubPipelineService:
    """Stub pipeline service for regenerate endpoint wiring tests."""

    def __init__(
        self,
        *,
        found_without_anchors: int = 3,
        extract_results: list | None = None,
    ) -> None:
        self.found_without_anchors = found_without_anchors
        self.extract_results = extract_results or [
            {"success": True, "youtube_id": "vid-a", "run_id": "run-1"},
            {"success": True, "youtube_id": "vid-b", "run_id": "run-2"},
            {"success": False, "youtube_id": "vid-c", "error": "extract failed"},
        ]
        self.regenerate_calls: list[str] = []

    async def run_bulk_extract_anchors(
        self,
        amount,
        *,
        extractor,
        text_model=None,
        skip_youtube_ids=None,
    ):
        return {
            "success": True,
            "requested": amount,
            "found_without_anchors": self.found_without_anchors,
            "processed": len(self.extract_results),
            "anchors_extracted": sum(1 for r in self.extract_results if r.get("success")),
            "anchors_failed": sum(1 for r in self.extract_results if not r.get("success")),
            "results": self.extract_results,
            "message": (
                f"Requested {amount} transcripts without anchors; "
                f"found {self.found_without_anchors}; processed {len(self.extract_results)}."
            ),
        }

    def regenerate_article_from_anchors(
        self,
        youtube_id,
        *,
        journalist,
        tone,
        article_type,
        text_model=None,
    ):
        self.regenerate_calls.append(youtube_id)
        if youtube_id == "vid-b":
            return {"success": False, "error": "generation failed", "youtube_id": youtube_id}
        return {
            "success": True,
            "mode": "updated",
            "article_id": 10 if youtube_id == "vid-a" else 11,
            "youtube_id": youtube_id,
            "content_len": 100,
            "bullets_count": 2,
        }


class StubWordPressSyncService:
    def __init__(self) -> None:
        self.sync_calls: list[tuple[str, bool]] = []

    def sync_regenerated_article_to_wordpress(self, youtube_id: str, *, created: bool):
        self.sync_calls.append((youtube_id, created))
        return {
            "success": True,
            "youtube_id": youtube_id,
            "wordpress_response": {"post_id": 999},
        }


def _articles_by_youtube_id():
    return {
        "vid-a": {"id": 10, "youtube_id": "vid-a"},
        "vid-b": {"id": 11, "youtube_id": "vid-b"},
    }


def _build_test_client(
    pipeline_service: RegenerateStubPipelineService,
    *,
    articles: dict | None = None,
    wp_service: StubWordPressSyncService | None = None,
) -> TestClient:
    articles = articles if articles is not None else _articles_by_youtube_id()
    wp_service = wp_service or StubWordPressSyncService()

    mock_db = MagicMock()

    def get_article_by_youtube_id(youtube_id: str):
        return articles.get(youtube_id)

    mock_db.get_article_by_youtube_id.side_effect = get_article_by_youtube_id

    def get_test_deps(_request=None):
        return SimpleNamespace(
            database=mock_db,
            transcript_manager=None,
            article_generator=None,
            journalist_manager=None,
            articles_db={},
            wordpress_sync_service=wp_service,
            pipeline_service=pipeline_service,
            image_service=None,
        )

    app.dependency_overrides[AppDependencies] = get_test_deps
    return TestClient(app, raise_server_exceptions=False)


def _clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()


def test_regenerate_endpoint_reports_requested_vs_found() -> None:
    stub = RegenerateStubPipelineService(found_without_anchors=3)
    with _build_test_client(stub) as client:
        response = client.post(
            "/pipeline/regenerate/8",
            params={"sync_to_wordpress": False},
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 8
    assert payload["found_without_anchors"] == 3
    assert payload["anchors_extracted"] == 2
    assert payload["anchors_failed"] == 1
    assert payload["articles_regenerated"] == 1
    assert payload["articles_failed"] == 1
    assert payload["wordpress_synced"] == 0
    assert "Requested 8" in payload["message"]
    assert "found 3" in payload["message"]


def test_regenerate_creates_when_no_local_article() -> None:
    stub = RegenerateStubPipelineService(
        found_without_anchors=1,
        extract_results=[{"success": True, "youtube_id": "vid-missing", "run_id": "run-x"}],
    )

    def regenerate_with_create(youtube_id, **kwargs):
        stub.regenerate_calls.append(youtube_id)
        return {
            "success": True,
            "mode": "created",
            "article_id": 99,
            "youtube_id": youtube_id,
            "content_len": 50,
            "bullets_count": 1,
        }

    stub.regenerate_article_from_anchors = regenerate_with_create

    with _build_test_client(stub, articles={}) as client:
        response = client.post(
            "/pipeline/regenerate/1",
            params={"sync_to_wordpress": False},
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["articles_regenerated"] == 1
    assert payload["results"][0]["regenerate"]["mode"] == "created"
    assert payload["results"][0]["article_id"] == 99
    assert stub.regenerate_calls == ["vid-missing"]


def test_regenerate_syncs_body_when_enabled() -> None:
    stub = RegenerateStubPipelineService(
        found_without_anchors=1,
        extract_results=[{"success": True, "youtube_id": "vid-a", "run_id": "run-1"}],
    )
    wp_stub = StubWordPressSyncService()
    with _build_test_client(stub, wp_service=wp_stub) as client:
        response = client.post(
            "/pipeline/regenerate/1",
            params={"sync_to_wordpress": True},
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["wordpress_synced"] == 1
    assert wp_stub.sync_calls == [("vid-a", False)]
    assert payload["results"][0]["wordpress"]["success"] is True


def test_regenerate_sync_false_skips_wordpress() -> None:
    stub = RegenerateStubPipelineService(
        found_without_anchors=1,
        extract_results=[{"success": True, "youtube_id": "vid-a", "run_id": "run-1"}],
    )
    wp_stub = StubWordPressSyncService()
    with _build_test_client(stub, wp_service=wp_stub) as client:
        response = client.post(
            "/pipeline/regenerate/1",
            params={"sync_to_wordpress": False},
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    assert wp_stub.sync_calls == []
    assert response.json()["results"][0]["wordpress"] is None
