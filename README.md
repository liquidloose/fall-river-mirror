# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror

**License:** This project is licensed under the [Polyform Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) license. Noncommercial use is free; commercial use is prohibited without permission. See [LICENSE](LICENSE) for full terms.

## Table of contents

- [Overview](#overview)
- [Getting started](#getting-started)
  - [Required credential files](#required-credential-files)
  - [Building Docker images](#building-docker-images)
  - [Running the environment](#running-the-environment)
  - [Refresh Python dependencies in profile-based Docker setups](#refresh-python-dependencies-in-profile-based-docker-setups)
- [Development vs production mode](#development-vs-production-mode)
  - [Goal](#goal)
  - [Two modes](#two-modes)
  - [Env / config](#env--config)
  - [Docker Compose](#docker-compose)
  - [Usage summary](#usage-summary)
- [Features](#features)
- [API endpoints](#api-endpoints)
- [API documentation](#api-documentation)
- [Database](#database)
  - [Transcript caching](#transcript-caching)
- [What can delete articles or transcripts](#what-can-delete-articles-or-transcripts)
  - [Articles](#articles)
  - [Transcripts](#transcripts)
  - [Schema](#schema)
  - [If both articles and transcripts dropped together](#if-both-articles-and-transcripts-dropped-together)
  - [How to check after the fact](#how-to-check-after-the-fact)
- [Planned API layout (router split)](#planned-api-layout-router-split)
- [AI creator architecture](#ai-creator-architecture)
- [Project structure](#project-structure)
- [Development](#development)
- [Helpful tips](#helpful-tips)
- [Troubleshooting](#troubleshooting)

## Overview

This project provides a development environment for The Fall River Mirror with:

- **FastAPI backend**: Python API with AI-powered article generation
- **WordPress frontend**: Content management system
- **Docker environment**: Profile-based Compose (`dev` vs `prod`) — see [Development vs production mode](#development-vs-production-mode)
- **Transcript caching**: Intelligent YouTube transcript storage and retrieval
- **CRUD operations**: Full create, read, update, delete API for articles

## Getting started

Change the name of the file `.env.sample` to `.env` and adjust the values accordingly.

### Required credential files

You will need to create the following three credential files in the project root directory. These files are not included in the repository for security reasons:

1. **`client_secret.json`** — Google OAuth credentials file
   - Contains your Google OAuth client ID, client secret, and project configuration
   - Get this from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   - Format: Standard Google OAuth credentials JSON file

2. **`youtube_token.json`** — YouTube API OAuth token
   - Contains your YouTube API access token and refresh token
   - Generated during the OAuth authentication flow
   - Format: JSON file with token, refresh_token, client_id, client_secret, and scopes

3. **`youtube_cookies.txt`** — YouTube session cookies
   - Contains browser cookies for YouTube authentication
   - Used for accessing YouTube content that requires authentication
   - Format: Netscape cookie file format

**Note:** These files are already listed in `.gitignore` and will not be committed to the repository. You must obtain the contents for these files yourself through the appropriate Google Cloud Console and OAuth setup processes.

In order to run this project, you will need to create two images with Docker.

### Building Docker images

The first one is the WordPress image. To build, use the following command:

```bash
docker build -t fr-mirror .
```

The second image you need to create is for the Python API. To build this one, enter the following command:

```bash
docker build -f Dockerfile.ai -t fr-mirror-ai .
```

### Running the environment

Now you are ready to create the environment. The sites will be available at localhost on the ports in your `.env` file.

Use the same [`docker-compose.yml`](docker-compose.yml) with Compose **profiles** — pass `--profile dev` or `--profile prod` so Compose starts the right services (see [Development vs production mode](#development-vs-production-mode) for detail).

- **Development (full stack):** `docker compose --profile dev up` — WordPress, MySQL, mirror-ai, Typesense, Caddy, etc. Use `.env`; set `WORDPRESS_BASE_URL` to your local WordPress (e.g. `http://wordpress:80` or `http://localhost:9004`).
- **Production:** `docker compose --profile prod up` — mirror-ai plus prod-oriented services (e.g. Typesense, Caddy); no local WordPress/MySQL. Load production overrides via `.env.prod` (e.g. `WORDPRESS_BASE_URL=https://fallrivermirror.com`).

### Refresh Python dependencies in profile-based Docker setups

If YouTube downloads start failing while transcript lookups still work, `yt-dlp` may be out of date in the running container. Rebuild the AI image for the active profile so dependencies from `requirements.txt` are reinstalled. Service names match [`docker-compose.yml`](docker-compose.yml) (e.g. `fr-mirror-ai`).

**Dev profile**

```bash
docker compose --profile dev build --no-cache fr-mirror-ai
docker compose --profile dev up -d fr-mirror-ai
docker compose --profile dev exec fr-mirror-ai python -m yt_dlp --version
```

**Prod profile**

```bash
docker compose --profile prod build --no-cache fr-mirror-ai
docker compose --profile prod up -d fr-mirror-ai
docker compose --profile prod exec fr-mirror-ai python -m yt_dlp --version
```

Notes:

- Use `--no-cache` when you suspect stale dependency layers.
- If your queue worker is a different service, replace `fr-mirror-ai` with that service name.
- `yt-dlp` is installed through `requirements.txt` during `Dockerfile.ai` image build.

## Development vs production mode

How the system is set up after the prod-only compose change.

### Goal

- **Development**: Full local stack — WordPress + MySQL + mirror-ai (FastAPI). FastAPI talks to local WordPress. Use local URLs in `.env`.
- **Production**: mirror-ai (FastAPI) plus prod support services (e.g. Typesense, Caddy); no local WordPress or MySQL. FastAPI talks to the live WordPress instance at fallrivermirror.com. Use production values in `.env.prod`.

### Two modes

| Aspect | Development | Production |
|--------|-------------|------------|
| **What runs** | mirror-ai + db + wordpress + my-wpcli + phpmyadmin (+ shared e.g. Typesense) | mirror-ai + Typesense + Caddy (no WordPress/MySQL) |
| **WordPress** | Local container (same compose network) | Not started; use live site |
| **MySQL** | Local container | Not started |
| **How to start** | `docker compose --profile dev up` (or `... down`) | `docker compose --profile prod up` (or `... down`) |
| **Env file** | `.env` (local values, e.g. `WORDPRESS_BASE_URL` to local IP or `http://wordpress:80`) | `.env.prod` (production values; `WORDPRESS_BASE_URL=https://fallrivermirror.com`) |

### Env / config

- **`.env`** — used by both modes. Contains all variables for the full stack and mirror-ai (API keys, DB, ports, etc.). For dev, set `WORDPRESS_BASE_URL` to your local WordPress (e.g. `http://wordpress:80` or `http://localhost:9004`).
- **`.env.prod`** — loaded by prod-profile services in [`docker-compose.yml`](docker-compose.yml) *after* `.env` so it overrides. Contains only the values that differ in production; at minimum `WORDPRESS_BASE_URL=https://fallrivermirror.com`.

Both modes use the same [`docker-compose.yml`](docker-compose.yml); pass `--profile dev` or `--profile prod` so Compose starts the right services.

### Docker Compose

- **Development**: [`docker-compose.yml`](docker-compose.yml) with `--profile dev` starts the full stack (WordPress, MySQL, dev tooling, mirror-ai, shared services such as Typesense). Dev mirror-ai may use additional env files as declared in compose (see `env_file` on each service).
- **Production**: Same file with `--profile prod` starts prod-oriented services (mirror-ai, Caddy, Typesense, etc.) and uses layered env files on those services so `.env.prod` overrides (e.g. `WORDPRESS_BASE_URL`).

### Usage summary

- **Dev:** `docker compose --profile dev up` or `docker compose --profile dev down` (from the directory containing `docker-compose.yml` and `.env`).
- **Prod:** `docker compose --profile prod up` or `docker compose --profile prod down` (same directory; keep `.env.prod` with production values, including `WORDPRESS_BASE_URL=https://fallrivermirror.com`).

## Features

### AI-powered article generation

- Generate articles using AI processing
- Support for different article types (Summary, Opinion/Editorial)
- Multiple writing tones (Friendly, Professional, Casual, Formal)
- Committee-specific content generation

### YouTube transcript integration

- **Intelligent caching**: Automatically stores transcripts in database
- **Fast retrieval**: Cached transcripts load 10–100x faster
- **Automatic storage**: New transcripts are automatically saved for future use
- **Database integration**: SQLite storage with full transcript management

### Full CRUD API

- **Create**: Generate new articles with AI
- **Read**: Retrieve articles with filtering and pagination
- **Update**: Modify existing articles (full and partial updates)
- **Delete**: Remove articles from the system (see [What can delete articles or transcripts](#what-can-delete-articles-or-transcripts))

### Database management

- SQLite database with automatic table creation
- Transcript caching and retrieval
- Article storage and management
- Committee and journalist tracking

## API endpoints

### Health check

- `GET /` — Server health status and database connection info

### Article generation

- `POST /article/generate/{context}/{prompt}/{article_type}/{tone}/{committee}` — Generate articles with path parameters

### Transcript management

- `GET /transcript/{youtube_id}` — Fetch YouTube transcripts with intelligent caching

### CRUD operations (articles)

- `POST /experimental/` — Create new article
- `GET /experimental/` — List all articles (with filtering and pagination)
- `GET /experimental/{article_id}` — Get specific article
- `PUT /experimental/{article_id}` — Update article (full update)
- `PATCH /experimental/{article_id}` — Update article (partial update)
- `DELETE /experimental/{article_id}` — Delete article

### YouTube crawler

- `GET /yt_crawler/{video_id}` — Process YouTube videos and generate articles

### WordPress

- `GET /wordpress/test-jwt` — Verify JWT against the configured WordPress base URL (e.g. fallrivermirror.com). Read-only; sends a GET to the article-youtube-ids endpoint and returns success/status. Does not create or modify any content.

Additional routes (sync, pipeline, images, dedupe, etc.) exist in the running app; see **Swagger UI** at `/docs` for the full list. The [Planned API layout (router split)](#planned-api-layout-router-split) section summarizes how routes are organized today vs. a future refactor.

## API documentation

Once your server is running, you can access:

- **Interactive API docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative docs**: `http://localhost:8000/redoc` (ReDoc)

## Database

The application uses SQLite with automatic table creation:

- **Database file**: `fr-mirror.db`
- **Tables**: `transcripts`, `articles`, `committees`, `journalists`, and related tables (see [Schema](#schema) under deletion reference)
- **Auto-initialization**: Tables are created automatically on first run

### Transcript caching

Transcripts are automatically cached in the database:

- **First request**: Fetches from YouTube API (~2–5 seconds)
- **Subsequent requests**: Retrieved from database (~10–50 ms)
- **Performance improvement**: 10–100x faster for cached transcripts

## What can delete articles or transcripts

Use this as a reference when investigating missing data (e.g. “250 articles and transcripts disappeared”).

### Articles

| Cause | How | Bulk? |
|-------|-----|--------|
| **DELETE /article/{article_id}** | Single article (and its art rows). | No — one per request. |
| **DELETE /articles/remove-duplicate-per-transcript** | For each transcript that has more than one article, keeps the oldest article and **deletes the rest**. | Yes — one request can delete many articles. **Does not delete any transcripts.** |

There is **no** other code path that deletes articles. No bulk delete by date, no cascade from transcripts.

### Transcripts

| Cause | How | Bulk? |
|-------|-----|--------|
| **DELETE /transcript/delete/{transcript_id}** | Single transcript by ID. | No — one per request. |

There is **no** bulk delete of transcripts in this app. No endpoint and no internal code that runs `DELETE FROM transcripts` without a single `id = ?`.

### Schema

Schema is defined in [`app/data/create_database.py`](app/data/create_database.py) (`Database._create_all_tables`). Relationships below match the declared SQLite foreign keys (none use `ON DELETE CASCADE`).

#### Legend

**Column tags (inside each box)**

| Tag | Meaning |
|-----|---------|
| **PK** | **Primary key** — uniquely identifies one row in that table (e.g. `transcripts.id`). |
| **FK** | **Foreign key** — stores an id (or key value) pointing at another table’s PK, linking rows together. |
| **UK** | **Unique key** — duplicates not allowed for that column (same idea as PK for uniqueness, but not necessarily “the” row id). |

**What the `*_id` fields mean (not just jargon)**

| Column | Points at | In plain English |
|--------|-----------|------------------|
| **`transcripts.id`** (PK on `transcripts`) | — | The internal row id for **one saved transcript** (caption/text + metadata for a YouTube video). **`DELETE /transcript/delete/{transcript_id}`** is this value. |
| **`articles.transcript_id`** | `transcripts.id` | **Which meeting transcript this article came from** — the article is the write-up; the transcript is the source recording/captures. |
| **`articles.id`** (PK on `articles`) | — | The internal row id for **one news article**. **`DELETE /article/{article_id}`** is this value. |
| **`art.transcript_id`** | `transcripts.id` (optional) | **Art linked to that meeting/transcript**, independent of whether you like the article row. |
| **`art.article_id`** | `articles.id` (optional) | **Art linked to that specific article** (e.g. illustration for that published story). |
| **`articles.journalist_id`** | `journalists.id` | **Which journalist is credited** for that article. |
| **`articles.committee`** | `committees.id` | **Which committee** the article is filed under (stored in a quirky way in SQLite — see DDL quirks below). |

**Relationship lines (Mermaid)**

Symbols are read **from the parent / “one” side toward the child / “many” side**. On each end of the line: **`||`** means **exactly one**, **`o{`** means **zero or more** (optional many).

So a line shaped like **`Something ||--o{ SomethingElse`** means **one-to-many** from left to right: each row on the right (**child**) references **one** row on the left (**parent**); each parent may have **zero or many** children. Reading from the child table toward the parent, that is **many-to-one**.

**Relationships in this diagram**

| From → To | Cardinality | Plain language |
|-----------|-------------|----------------|
| `committees` → `articles` | One-to-many | Many articles under one committee; each article points to **one** committee row. |
| `journalists` → `articles` | One-to-many | Many articles by one journalist; each article points to **one** journalist. |
| `transcripts` → `articles` | One-to-many | Several articles can incorrectly point at the **same** source transcript until deduped; each article still means “I summarize **this** transcript row.” |
| `transcripts` → `art` | One-to-many | Several **images** can be associated with the **same** meeting transcript (`art.transcript_id`). |
| `articles` → `art` | One-to-many | Several **images** can be associated with the **same** article (`art.article_id`). |

Tables **`video_queue`**, **`tones`**, and **`categories`** appear for context; they have **no foreign-key edges** in this diagram (`video_queue` is only loosely tied by `youtube_id`, and tone/category names are copied as **text** onto `articles`, not FK links).

```mermaid
erDiagram
    transcripts {
        int id PK
        text youtube_id
        text content
    }
    articles {
        int id PK
        text youtube_id
        int transcript_id FK
        text committee FK
        int journalist_id FK
        text title
        text content
    }
    art {
        int id PK
        int transcript_id FK
        int article_id FK
    }
    committees {
        int id PK
        text name
        text description
        text created_date
    }
    journalists {
        int id PK
        text full_name UK
    }
    video_queue {
        int id PK
        text youtube_id UK
        int transcript_available
    }
    tones {
        int id PK
        text name UK
    }
    categories {
        int id PK
        text name UK
    }

    committees ||--o{ articles : committee_to_id
    journalists ||--o{ articles : journalist_id
    transcripts ||--o{ articles : transcript_id
    transcripts ||--o{ art : transcript_id
    articles ||--o{ art : article_id
```

**DDL quirks**

- `articles.committee` is typed `TEXT` in SQLite DDL while referencing `committees(id)` (integer PK)—matches [`create_database.py`](app/data/create_database.py) as deployed.
- The **`committees`** table is referenced by `articles` and populated via `add_committee`; confirm your DB actually has this table (older/manual DDL vs fresh `_create_all_tables`).

**How this relates to deletes**

- Foreign keys do **not** use `ON DELETE CASCADE`. Deleting an article does **not** delete its transcript (or the reverse). Deleting a transcript does **not** remove related articles; `articles.transcript_id` can become a dangling reference unless something else updates or deletes those rows.
- **`art`**: Not cascade-deleted by SQLite. The API deletes linked `art` rows **explicitly** when removing an article (`delete_art_by_article_id` before `delete_article_by_id`). Transcript-only deletes do not clear `art` in application code—check DB if you care about orphaned `art.transcript_id`.
- **`video_queue`**: Shares `youtube_id` with transcripts logically; there is **no** foreign key between `video_queue` and `transcripts`.
- **`tones` / `categories`**: Enum-synced lookup tables. Article tone/type are stored as **`TEXT` on `articles`**, not FK columns in the schema.

### If both articles and transcripts dropped together

- **This app cannot do that.** It cannot bulk-delete transcripts, and the only bulk delete for articles (remove-duplicate-per-transcript) does not touch the `transcripts` table.
- Likely causes: **database file replaced or restored** (deploy, backup restore, wrong DB path, different server), or **external tool/script** (manual SQL, another service) that modified or replaced the DB.

### How to check after the fact

1. **app.log**  
   Search for:

   - `Removed duplicate articles` → remove-duplicate-per-transcript ran (deleted some articles only).
   - `Successfully deleted article` / `Successfully deleted transcript` → single deletes; count how many to see if it matches.

2. **Startup counts**  
   The app logs `Database counts at startup: transcripts=N, articles=N`. If you have log rotation or archives, compare before/after an incident.

3. **Who can call the API**  
   Check crontabs, GitHub Actions, scripts, or other services that might call `DELETE /article/{id}` or `DELETE /transcript/delete/{id}` or `DELETE /articles/remove-duplicate-per-transcript`.

## Planned API layout (router split)

Short reference for when we implement the refactor (from a codebase planning pass).

### Current state

- All ~35 API routes live in `app/main.py` (~3.3k lines).
- No `APIRouter` usage; everything is mounted on `app` directly.
- Harder to navigate, test, and change one area without touching the rest.

### Goal

Split routes by domain into separate router modules and keep `main.py` as a thin app factory + startup (DB init, journalist init, etc.).

### Target layout

```mermaid
flowchart LR
  subgraph main [main.py]
    App[FastAPI app]
    Init[DB and journalist init]
    State[app.state]
    Mount[include_router x 8]
  end
  subgraph deps [app/dependencies.py]
    AppDeps[AppDependencies class]
  end
  subgraph routers [app/routers/]
    Health[health.py]
    Transcripts[transcripts.py]
    Articles[articles.py]
    Images[images.py]
    Queue[queue.py]
    Pipeline[pipeline.py]
    WordPress[wordpress.py]
    Journalist[journalist.py]
    Crawler[crawler.py]
  end
  subgraph services [app/services - classes]
    WordPressSyncService[WordPressSyncService]
    PipelineService[PipelineService]
    ImageService[ImageService]
  end
  App --> Init
  Init --> State
  State --> deps
  State --> services
  App --> Mount
  Mount --> routers
  routers --> deps
  WordPress --> WordPressSyncService
  Pipeline --> PipelineService
  Pipeline --> WordPressSyncService
  PipelineService --> ImageService
  Images --> ImageService
```

### Suggested router breakdown

| Router / module | Responsibility |
|-----------------|----------------|
| **Health** | `GET /` (health check) |
| **Transcripts** | `GET /transcript/fetch/{youtube_id}`, `DELETE /transcript/delete/{transcript_id}`, `POST /transcript/fetch/{amount}`, `GET /transcripts/without-articles` |
| **Articles** | `GET /articles/`, `GET /articles/{article_id}`, `GET /articles/count`, `PUT /articles/{article_id}`, `PATCH /articles/{article_id}`, `DELETE /article/{article_id}`, `DELETE /articles/remove-duplicate-per-transcript`, `POST /articles/strip-h1-tags`, `POST /articles/strip-fall-river-from-titles`, article generation and manual create, `POST /article/write/{amount_of_articles}`, `PATCH /article/{article_id}/bullet-points`, `POST /bullet-points/generate/batch/{amount_of_articles}` |
| **Images / art** | `POST /image/generate/...`, `GET /image/{art_id}`, `DELETE /image/delete/{art_id}`, `DELETE /art/delete-all`, `DELETE /art/cleanup-duplicates`, `PATCH /image/{art_id}/regenerate` |
| **Queue / pipeline** | `POST /queue/build`, `POST /queue/cleanup`, `GET /queue/stats`, `DELETE /queue/clear`, `POST /pipeline/run`, `GET /transcripts/pending/{journalist}` |
| **WordPress sync** | `POST /sync-article-to-wordpress/{article_id}`, `POST /sync-articles-to-wordpress`, `POST /sync-missing-articles-to-wordpress` |
| **Journalist** | `GET /journalist/{journalist_name}` |
| **YouTube crawler** | `GET /yt_crawler/{video_id}` |

### Implementation approach

1. Create `app/routers/` (e.g. `__init__.py` plus one file per domain or a few grouped files).
2. Move route handlers and their immediate helpers from `main.py` into the right router module. Pass shared dependencies (e.g. `database`, `transcript_manager`, `article_generator`) via router constructor or dependency injection.
3. In `main.py`, create each router and call `app.include_router(router, prefix=..., tags=[...])` (prefix optional).
4. Keep in `main.py`: app creation, logging config, env/config, DB and journalist init, and any shared helpers used by multiple routers (or move those to `app/utils` or `app/core` if they grow).
5. Run tests and manual smoke checks; fix imports and any broken references.

### Related (do later or in parallel)

- **Article storage**: Several article endpoints still use in-memory `articles_db`; migrating them to the SQLite `articles` table is a separate P0 item (see plan discussion in project docs).
- **README**: After refactor, consider a short “Architecture” or “API structure” section pointing to `app/routers/` and `main.py`.

## AI creator architecture

The project uses a singleton-based class hierarchy for AI content creators (journalists, artists, etc.). This architecture provides:

- **Consistent identity** — Each creator has fixed traits (name, slant, style)
- **Flexible output** — Mutable attributes can be overridden at runtime
- **Shared functionality** — Common methods inherited from base classes
- **Type safety** — Clear contracts for what subclasses must implement

### Class hierarchy

```
BaseCreator (ABC)
├── BaseJournalist
│   └── AureliusStone
└── BaseArtist
    └── SpectraVeritas
```

### BaseCreator

The abstract base class for all AI creators. Implements singleton pattern per subclass.

**Fixed identity traits** (class constants, defined by subclasses):

- `FIRST_NAME`, `LAST_NAME`, `FULL_NAME`, `NAME`
- `SLANT` — Political/editorial perspective
- `STYLE` — Writing/artistic style

**Shared methods**:

- `get_bio()` — Loads bio from `context_files/bios/{name}_bio.txt`
- `get_description()` — Loads description from `context_files/descriptions/{name}_description.txt`
- `get_base_personality()` — Returns dict of core traits
- `_load_attribute_context()` — Helper to load context files

**Abstract methods** (must be implemented by subclasses):

- `load_context()` — Load relevant context files
- `get_personality()` — Get full personality including subclass traits
- `get_full_profile()` — Return complete creator profile

### BaseJournalist

Extends BaseCreator with article-specific functionality.

**Additional traits**:

- `DEFAULT_TONE` — e.g., `Tone.ANALYTICAL`
- `DEFAULT_ARTICLE_TYPE` — e.g., `ArticleType.OP_ED`

**Key methods**:

- `generate_article(context, user_content)` — Generate article via xAI
- `get_guidelines()` — Override for journalist-specific rules
- `get_system_prompt(context)` — Build AI system prompt

### BaseArtist

Extends BaseCreator with image-specific functionality.

**Additional traits**:

- `DEFAULT_MEDIUM` — e.g., "digital", "watercolor"
- `DEFAULT_AESTHETIC` — e.g., "surrealist", "minimalist"

**Key methods**:

- `generate_image(context, prompt)` — Generate image via xAI Aurora
- `load_context()` — Load medium/aesthetic context files

### Usage example

```python
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_artists.spectra_veritas import SpectraVeritas

# Singleton - same instance every time
journalist = AureliusStone()
artist = SpectraVeritas()

# Override mutable attributes at instantiation
artist_watercolor = SpectraVeritas(medium="watercolor", aesthetic="impressionist")

# Generate content
article = journalist.generate_article(context="...", user_content="")
image = artist.generate_image(context="...", prompt="A city council meeting")
```

### Adding a new creator

1. Create class in appropriate folder (`ai_journalists/` or `ai_artists/`)
2. Inherit from `BaseJournalist` or `BaseArtist`
3. Define required class constants (identity traits)
4. Override `get_guidelines()` or other methods as needed
5. Add bio/description files to `context_files/`

```python
class NewJournalist(BaseJournalist):
    FIRST_NAME = "Jane"
    LAST_NAME = "Doe"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "progressive"
    STYLE = "investigative"

    DEFAULT_TONE = Tone.CRITICAL
    DEFAULT_ARTICLE_TYPE = ArticleType.INVESTIGATIVE

    def get_guidelines(self) -> str:
        return "- Focus on accountability..."
```

## Project structure

```
app/
├── main.py                          # FastAPI application and endpoints (planned: thin factory + router includes — see Planned API layout)
├── data/
│   ├── create_database.py           # Database management
│   ├── enum_classes.py              # Enums (Tone, ArticleType, etc.)
│   └── transcript_manager.py        # YouTube transcript handling
└── content_department/
    ├── ai_journalists/
    │   ├── base_journalist.py       # BaseJournalist class
    │   └── aurelius_stone.py        # Journalist implementation
    ├── ai_artists/
    │   ├── base_artist.py           # BaseArtist class
    │   └── spectra_veritas.py       # Artist implementation
    └── creation_tools/
        ├── base_creator.py          # BaseCreator ABC
        ├── xai_text_query.py        # Text generation API
        ├── xai_image_query.py       # Image generation API
        └── context_files/           # Context/prompt files
```

## Development

### Running tests

From the project root (where `requirements.txt` and `app/` live), run the test suite with [pytest](https://docs.pytest.org/):

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run a specific test file or directory
pytest tests/integration/api/
pytest tests/unit/data/test_transcript_manager.py
```

Install test dependencies first if needed: `pip install -r requirements.txt` (pytest, pytest-cov, pytest-asyncio, and related packages are already listed there).

#### How the tests work

- **Dependency overrides:** The app exposes a single dependency, `get_app_deps`, that provides the database, transcript manager, article generator, and related state. In tests, that dependency is overridden so every request gets a **test double**: a real in-memory SQLite database plus mocks for external services (YouTube, WordPress, etc.). No production DB or APIs are touched. See `tests/conftest.py` for the `client` fixture and `_make_test_deps`.
- **Layers:**
  - **Unit tests** (`tests/unit/`) exercise one class or module in isolation with mocks (e.g. `TranscriptManager` with a fake DB and patched YouTube API).
  - **API integration tests** (`tests/integration/api/`) call routes via FastAPI’s `TestClient` using the overridden deps; they assert status codes and response shape.
  - **Database integration tests** (`tests/integration/database/`) use an in-memory `Database` instance and assert schema and CRUD against the current production schema.
- **In-memory DB:** All test databases use `Database(":memory:")`, so nothing is written to disk and runs stay fast.
- When something fails, the failing test name and file usually narrow it down: a unit test points at the class under test; an API test points at the route or the test double’s configuration.

**Manual DB check when logs aren’t enough:** `manual_database_test.py` talks to your **real** database (`fr-mirror.db`). It writes one test transcript row, verifies it, then deletes it. Use it to confirm the DB and transcript caching path when things go wrong. Run: `python manual_database_test.py` (it will prompt before writing).

### Adding new endpoints

Today, endpoints live in `main.py`. After the [Planned API layout (router split)](#planned-api-layout-router-split), add handlers in the appropriate module under `app/routers/` and register the router from `main.py`.

Until then:

1. Add endpoint in `main.py`
2. Implement business logic in `utils.py`
3. Add database methods in `database.py` if needed
4. Update documentation

### Database operations

- All database operations are logged
- Automatic connection management
- Error handling and recovery
- Health check endpoints available

## Helpful tips

### Server reload command

### Scheduled pipeline (GitHub Actions)

The workflow `.github/workflows/trigger-pipeline.yml` runs every 15 minutes and POSTs to your deployed API’s `/pipeline/run` endpoint. For it to work, add a repository secret in GitHub (Settings → Secrets and variables → Actions):

- **`PIPELINE_API_URL`** — Base URL of your API with no trailing slash (e.g. `http://YOUR_DROPLET_IP:3004` or `https://your-domain.com`). The workflow appends `/pipeline/run?...` to this.

Scheduled runs use the default branch; ensure the workflow file is on that branch.

**Alternative: cron on the server (e.g. DigitalOcean Droplet)**  
If the API runs on the same machine, use crontab for a reliable schedule (e.g. every 15 minutes):

```bash
crontab -e
```

Add (API on port 3004, same host). Use full path to `curl` so cron finds it; the `echo` ensures a log line even if the request fails:

```cron
*/15 * * * * echo "$(date -u) pipeline cron start" >> /tmp/pipeline-cron.log 2>&1; /usr/bin/curl -sSf -o /tmp/pipeline-response.json -w "\n\%{http_code}" -X POST "http://127.0.0.1:3004/pipeline/run?amount=2&queue_mode=Use%20Whisper&auto_build=true&journalist=FRJ1&tone=professional&article_type=news&model=gpt-image-1&sync_to_wordpress=true" >> /tmp/pipeline-cron.log 2>&1
```

If `curl` is elsewhere, run `which curl` and use that path. In crontab, `%` is special (turns into newline), so the curl format must use `\%{http_code}` not `%{http_code}`. Check that `crond` is running: `systemctl status crond`. View cron output: `tail -f /tmp/pipeline-cron.log`.

**Test cron (runs every minute, appends to a log):**

```cron
* * * * * echo "$(date -u) hello world" >> /tmp/hello-cron.log 2>&1
```

After a few minutes, `cat /tmp/hello-cron.log` or `tail -f /tmp/hello-cron.log` to confirm. Remove the line from crontab when done testing.

### Testing the API

You can test the endpoints using:

- **Browser**: Direct URL access for GET endpoints
- **curl**: Command-line testing
- **Python requests**: Programmatic testing
- **Swagger UI**: Interactive testing at `/docs`

### Example API calls

```bash
# Generate an article
curl -X POST "http://localhost:8000/article/generate/AI%20basics/Explain%20machine%20learning/SUMMARY/PROFESSIONAL/PLANNING_BOARD"

# Get a transcript (will cache automatically)
curl "http://localhost:8000/transcript/VjaU4DAxP6s"

# Create an article via CRUD API
curl -X POST "http://localhost:8000/experimental/" \
  -H "Content-Type: application/json" \
  -d '{"context": "AI in healthcare", "prompt": "Write about AI applications", "article_type": "SUMMARY", "tone": "PROFESSIONAL", "committee": "PLANNING_BOARD"}'
```

### Debugging tips

**When endpoints won't load**: Use the server reload command above with `--log-level debug` to see detailed Python errors and stack traces that can help identify issues.

```text
uvicorn app.main:app --host 0.0.0.0 --port 80 --reload --log-level debug
```

### Log levels

Here are the log levels:

1. **debug**: Shows the most detailed information, useful for development and troubleshooting
2. **info**: (Default) Shows general operational information
3. **warning**: Shows only warning and error messages
4. **error**: Shows only error messages
5. **critical**: Shows only critical error messages

### Imports cannot be found

If the ms-python language support displays red, squiggly lines underneath the imports and says something like "import can't be found", then run this command:

`which python`

If the output is anything besides 3.13, then you need to change your language interpreter to the 3.13 one in VS Code/Cursor.

## Troubleshooting

### Common issues

1. **Database connection errors**: Check file permissions and disk space
2. **Import errors**: Verify Python interpreter and dependencies
3. **Endpoint not found**: Check server logs and endpoint definitions
4. **Transcript caching not working**: Verify database initialization and table creation

### Debug commands

```python
# Check database health
from app.database import Database
db = Database("fr-mirror")
db.check_database_health()

# Check database state
db.get_database_state()
```
