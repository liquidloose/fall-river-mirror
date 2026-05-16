# HTTP API architecture

How the Fall River Mirror FastAPI application is structured after the router and service-layer refactor.

For the full narrative (diagram, router table, testing notes), see [**Application architecture**](../README.md#application-architecture) in the README.

## Summary

| Layer | Location | Role |
|-------|----------|------|
| App factory | [`app/main.py`](../app/main.py) | Logging, middleware, DB init, enum sync, journalists, service instances, `app.state`, `include_router` |
| Dependencies | [`app/dependencies.py`](../app/dependencies.py) | `AppDependencies` — `Depends(AppDependencies)` in routers |
| Routes | [`app/routers/`](../app/routers/) | Domain `APIRouter` modules |
| Orchestration | [`app/services/`](../app/services/) | `PipelineService`, `WordPressSyncService`, `ImageService` |

## Routers

| Module | Purpose |
|--------|---------|
| `health.py` | Health check |
| `transcripts.py` | Transcript CRUD/fetch/list/pending |
| `articles.py` | Articles, generation, bullet points |
| `images.py` | Art/image endpoints |
| `queue.py` | Video queue maintenance |
| `pipeline.py` | `POST /pipeline/run` |
| `wordpress.py` | WordPress sync and repair helpers |
| `journalist.py` | Journalist metadata |
| `crawler.py` | YouTube crawler |
| `editor.py` | Spell-check, fact-check, related tooling |

## Testing

[`tests/conftest.py`](../tests/conftest.py) overrides **`AppDependencies`** so routes receive an in-memory DB and mocks.

## Historical note

Earlier drafts of this document tracked a **planned** split of `main.py` into routers. That split is **implemented**; use this file and the README section above as the source of truth.
