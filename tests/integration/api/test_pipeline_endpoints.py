"""Integration tests for pipeline endpoint model controls and aliases."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.data.enum_classes import ImageModel, TextModel
from app.dependencies import AppDependencies
from app.main import app


class StubPipelineService:
    """Minimal pipeline service stub for endpoint wiring tests."""

    def __init__(self) -> None:
        self.extract_call = None
        self.write_call = None
        self.image_call = None

    async def run_build_queue(self, channel_url, amount, skip_youtube_ids_on_wp=None):
        return {"success": True, "message": "ok", "results": {"newly_queued": 0}}

    async def run_bulk_fetch_transcripts(
        self,
        amount,
        auto_build,
        channel_url=None,
        skip_youtube_ids_on_wp=None,
        include_whisper_items=True,
    ):
        return {
            "success": True,
            "transcripts_fetched": 1,
            "transcripts_failed": 0,
            "results": [],
        }

    async def run_bulk_extract_anchors(
        self,
        amount,
        *,
        extractor,
        text_model=None,
        skip_youtube_ids=None,
    ):
        self.extract_call = {
            "amount": amount,
            "extractor": extractor,
            "text_model": text_model,
        }
        return {
            "success": True,
            "anchors_extracted": 1,
            "anchors_failed": 0,
            "results": [],
        }

    async def run_bulk_write_articles(
        self,
        amount,
        journalist,
        tone,
        article_type,
        skip_youtube_ids=None,
        text_model=None,
    ):
        self.write_call = {
            "amount": amount,
            "text_model": text_model,
        }
        return {
            "success": True,
            "articles_generated": 1,
            "articles_failed": 0,
            "results": [],
        }

    def run_bullet_points_batch(self, amount):
        return {"processed": 1, "skipped": 0, "errors": []}

    def run_image_batch(self, amount, artist, model, snippet_text_model=None):
        self.image_call = {
            "amount": amount,
            "artist": artist,
            "model": model,
            "snippet_text_model": snippet_text_model,
        }
        return {
            "success": True,
            "images_generated": 1,
            "images_failed": 0,
            "results": [],
        }


def _build_test_client(pipeline_service: StubPipelineService) -> TestClient:
    def get_test_deps(_request=None):
        return SimpleNamespace(
            database=object(),
            transcript_manager=None,
            article_generator=None,
            journalist_manager=None,
            articles_db={},
            wordpress_sync_service=None,
            pipeline_service=pipeline_service,
            image_service=None,
        )

    app.dependency_overrides[AppDependencies] = get_test_deps
    return TestClient(app, raise_server_exceptions=False)


def _clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()


def test_pipeline_run_routes_explicit_models() -> None:
    """Explicit params route model selection to each stage."""
    stub = StubPipelineService()
    with _build_test_client(stub) as client:
        response = client.post(
            "/pipeline/run",
            params={
                "amount": 1,
                "queue_mode": "Skip Whisper",
                "sync_to_wordpress": False,
                "journalist_text_model": TextModel.CLAUDE_HAIKU_4_5.value,
                "image_model": ImageModel.GROK.value,
                "extractor_text_model": TextModel.GEMINI_2_5_FLASH.value,
                "snippet_text_model": TextModel.CLAUDE_HAIKU_4_5.value,
            },
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["model_selection"]["journalist_text_model"]
        == TextModel.CLAUDE_HAIKU_4_5.value
    )
    assert payload["model_selection"]["image_model"] == ImageModel.GROK.value
    assert stub.write_call["text_model"] == TextModel.CLAUDE_HAIKU_4_5
    assert stub.image_call["model"] == ImageModel.GROK
    assert stub.image_call["snippet_text_model"] == TextModel.CLAUDE_HAIKU_4_5
    assert stub.extract_call["text_model"] == TextModel.GEMINI_2_5_FLASH


def test_pipeline_run_uses_default_models_and_queue_mode() -> None:
    """Pipeline defaults match the documented endpoint contract."""
    stub = StubPipelineService()
    with _build_test_client(stub) as client:
        response = client.post(
            "/pipeline/run",
            params={
                "amount": 1,
                "sync_to_wordpress": False,
            },
        )
    _clear_dependency_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_mode"] == "Use Whisper"
    assert (
        payload["model_selection"]["extractor_text_model"]
        == TextModel.GEMINI_2_5_PRO.value
    )
    assert (
        payload["model_selection"]["journalist_text_model"]
        == TextModel.GEMINI_3_5_FLASH.value
    )
    assert (
        payload["model_selection"]["snippet_text_model"]
        == TextModel.GEMINI_2_5_FLASH.value
    )
    assert payload["model_selection"]["image_model"] == ImageModel.GPT_IMAGE_1.value
    assert stub.extract_call["text_model"] == TextModel.GEMINI_2_5_PRO
    assert stub.write_call["text_model"] == TextModel.GEMINI_3_5_FLASH
    assert stub.image_call["model"] == ImageModel.GPT_IMAGE_1
    assert stub.image_call["snippet_text_model"] == TextModel.GEMINI_2_5_FLASH


def test_pipeline_openapi_hides_legacy_model_alias_params() -> None:
    """OpenAPI no longer documents legacy model aliases."""
    stub = StubPipelineService()
    with _build_test_client(stub) as client:
        response = client.get("/openapi.json")
    _clear_dependency_overrides()

    assert response.status_code == 200
    openapi = response.json()
    params = openapi["paths"]["/pipeline/run"]["post"]["parameters"]
    param_names = {param["name"] for param in params}
    assert "text_model" not in param_names
    assert "model" not in param_names
