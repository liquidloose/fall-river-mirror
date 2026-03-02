# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror

**License:** This project is licensed under the [Polyform Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) license. Noncommercial use is free; commercial use is prohibited without permission. See [LICENSE](LICENSE) for full terms.

## Overview

This project provides a development environment for The Fall River Mirror with:
- **FastAPI Backend**: Python API with AI-powered article generation
- **WordPress Frontend**: Content management system
- **Docker Environment**: Containerized development setup
- **Transcript Caching**: Intelligent YouTube transcript storage and retrieval
- **CRUD Operations**: Full Create, Read, Update, Delete API for articles

## Features

### 🧠 AI-Powered Article Generation
- Generate articles using AI processing
- Support for different article types (Summary, Opinion/Editorial)
- Multiple writing tones (Friendly, Professional, Casual, Formal)
- Committee-specific content generation

### 📹 YouTube Transcript Integration
- **Intelligent Caching**: Automatically stores transcripts in database
- **Fast Retrieval**: Cached transcripts load 10-100x faster
- **Automatic Storage**: New transcripts are automatically saved for future use
- **Database Integration**: SQLite storage with full transcript management

### 🔄 Full CRUD API
- **Create**: Generate new articles with AI
- **Read**: Retrieve articles with filtering and pagination
- **Update**: Modify existing articles (full and partial updates)
- **Delete**: Remove articles from the system

### 🗄️ Database Management
- SQLite database with automatic table creation
- Transcript caching and retrieval
- Article storage and management
- Committee and journalist tracking


## Getting Started

Change the name of the file `.env.sample` to `.env` and adjust the values accordingly.

### Required Credential Files

You will need to create the following three credential files in the project root directory. These files are not included in the repository for security reasons:

1. **`client_secret.json`** - Google OAuth credentials file
   - Contains your Google OAuth client ID, client secret, and project configuration
   - Get this from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   - Format: Standard Google OAuth credentials JSON file

2. **`youtube_token.json`** - YouTube API OAuth token
   - Contains your YouTube API access token and refresh token
   - Generated during the OAuth authentication flow
   - Format: JSON file with token, refresh_token, client_id, client_secret, and scopes

3. **`youtube_cookies.txt`** - YouTube session cookies
   - Contains browser cookies for YouTube authentication
   - Used for accessing YouTube content that requires authentication
   - Format: Netscape cookie file format

**Note:** These files are already listed in `.gitignore` and will not be committed to the repository. You must obtain the contents for these files yourself through the appropriate Google Cloud Console and OAuth setup processes.

In order to run this project, you will need to create two images with Docker.

### Building Docker Images

The first one is the WordPress image. To build, use the following command:
```bash
docker build -t fr-mirror .
```

The second image you need to create is for the Python API. To build this one, enter the
following command:
```bash
docker build -f Dockerfile.ai -t fr-mirror-ai .
```

### Running the Environment

Now you are ready to create the environment! The sites will be available at localhost on the ports in your `.env` file.

- **Dev (full stack):** `docker compose up` — WordPress, MySQL, and mirror-ai; uses `.env` (set `WORDPRESS_BASE_URL` to your local WordPress, e.g. `http://wordpress:80` or `http://localhost:9004`).
- **Production (mirror-ai only):** `docker compose -f docker-compose.prod.yml up` — uses `.env` plus `.env.prod` (override `WORDPRESS_BASE_URL=https://fallrivermirror.com`). See [docs/plan-dev-production-mode.md](docs/plan-dev-production-mode.md) for details.


## API Endpoints

### Health Check
- `GET /` - Server health status and database connection info

### Article Generation
- `POST /article/generate/{context}/{prompt}/{article_type}/{tone}/{committee}` - Generate articles with path parameters

### Transcript Management
- `GET /transcript/{youtube_id}` - Fetch YouTube transcripts with intelligent caching

### CRUD Operations (Articles)
- `POST /experimental/` - Create new article
- `GET /experimental/` - List all articles (with filtering and pagination)
- `GET /experimental/{article_id}` - Get specific article
- `PUT /experimental/{article_id}` - Update article (full update)
- `PATCH /experimental/{article_id}` - Update article (partial update)
- `DELETE /experimental/{article_id}` - Delete article

### YouTube Crawler
- `GET /yt_crawler/{video_id}` - Process YouTube videos and generate articles

## API Documentation

Once your server is running, you can access:
- **Interactive API Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative Docs**: `http://localhost:8000/redoc` (ReDoc)

## Database

The application uses SQLite with automatic table creation:
- **Database file**: `fr-mirror.db`
- **Tables**: `transcripts`, `articles`, `committees`, `journalists`
- **Auto-initialization**: Tables are created automatically on first run

### Transcript Caching
Transcripts are automatically cached in the database:
- **First request**: Fetches from YouTube API (~2-5 seconds)
- **Subsequent requests**: Retrieved from database (~10-50ms)
- **Performance improvement**: 10-100x faster for cached transcripts


## Helpful Tips

### Server Reload Command


### Testing the API

You can test the endpoints using:
- **Browser**: Direct URL access for GET endpoints
- **curl**: Command-line testing
- **Python requests**: Programmatic testing
- **Swagger UI**: Interactive testing at `/docs`

### Example API Calls

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

### 🔍 Debugging Tips

**When endpoints won't load**: 🔍  Use the server reload command above with `--log-level debug` to see detailed Python errors and stack traces that can help identify issues.
 
``` uvicorn app.main:app --host 0.0.0.0 --port 80 --reload --log-level debug
```

### Log Levels

Here are the log levels:
1. **debug**: Shows the most detailed information, useful for development and troubleshooting
2. **info**: (Default) Shows general operational information
3. **warning**: Shows only warning and error messages
4. **error**: Shows only error messages
5. **critical**: Shows only critical error messages

### Imports cannot be found
If the ms-python language support displays red, squiggly lines underneath the imports and says something like 
"import can't be found", then run this command:
`which python`
if the output is anything besides 3.13, then you need to change your language interpreter the 3.13 one in VScode/Cursor.

## AI Creator Architecture

The project uses a singleton-based class hierarchy for AI content creators (journalists, artists, etc.). This architecture provides:

- **Consistent identity** - Each creator has fixed traits (name, slant, style)
- **Flexible output** - Mutable attributes can be overridden at runtime
- **Shared functionality** - Common methods inherited from base classes
- **Type safety** - Clear contracts for what subclasses must implement

### Class Hierarchy

```
BaseCreator (ABC)
├── BaseJournalist
│   └── AureliusStone
└── BaseArtist
    └── SpectraVeritas
```

### BaseCreator

The abstract base class for all AI creators. Implements singleton pattern per subclass.

**Fixed Identity Traits** (class constants, defined by subclasses):
- `FIRST_NAME`, `LAST_NAME`, `FULL_NAME`, `NAME`
- `SLANT` - Political/editorial perspective
- `STYLE` - Writing/artistic style

**Shared Methods**:
- `get_bio()` - Loads bio from `context_files/bios/{name}_bio.txt`
- `get_description()` - Loads description from `context_files/descriptions/{name}_description.txt`
- `get_base_personality()` - Returns dict of core traits
- `_load_attribute_context()` - Helper to load context files

**Abstract Methods** (must be implemented by subclasses):
- `load_context()` - Load relevant context files
- `get_personality()` - Get full personality including subclass traits
- `get_full_profile()` - Return complete creator profile

### BaseJournalist

Extends BaseCreator with article-specific functionality.

**Additional Traits**:
- `DEFAULT_TONE` - e.g., `Tone.ANALYTICAL`
- `DEFAULT_ARTICLE_TYPE` - e.g., `ArticleType.OP_ED`

**Key Methods**:
- `generate_article(context, user_content)` - Generate article via xAI
- `get_guidelines()` - Override for journalist-specific rules
- `get_system_prompt(context)` - Build AI system prompt

### BaseArtist

Extends BaseCreator with image-specific functionality.

**Additional Traits**:
- `DEFAULT_MEDIUM` - e.g., "digital", "watercolor"
- `DEFAULT_AESTHETIC` - e.g., "surrealist", "minimalist"

**Key Methods**:
- `generate_image(context, prompt)` - Generate image via xAI Aurora
- `load_context()` - Load medium/aesthetic context files

### Usage Example

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

### Adding a New Creator

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

## Project Structure

```
app/
├── main.py                          # FastAPI application and endpoints
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

### Adding New Endpoints
1. Add endpoint in `main.py`
2. Implement business logic in `utils.py`
3. Add database methods in `database.py` if needed
4. Update documentation

### Database Operations
- All database operations are logged
- Automatic connection management
- Error handling and recovery
- Health check endpoints available

## Troubleshooting

### Common Issues
1. **Database connection errors**: Check file permissions and disk space
2. **Import errors**: Verify Python interpreter and dependencies
3. **Endpoint not found**: Check server logs and endpoint definitions
4. **Transcript caching not working**: Verify database initialization and table creation

### Debug Commands
```python
# Check database health
from app.database import Database
db = Database("fr-mirror")
db.check_database_health()

# Check database state
db.get_database_state()
```


