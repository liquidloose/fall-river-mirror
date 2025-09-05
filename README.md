# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror

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

Now you are ready to create the environment! Type `docker compose up` in your terminal from inside the directory where the Dockerfiles live. The sites will be available at localhost running on the ports that you specified in your .env file: `<your-ip/localhost-goes-here>:<your-port-number-goes-here>`


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
 
``` uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
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

## Project Structure

```
app/
├── main.py              # FastAPI application and endpoints
├── utils.py             # Utility functions and business logic
├── database.py          # Database management and operations
├── data_classes.py      # Pydantic models and data structures
├── crud_endpoints.py    # CRUD operations for articles
├── xai_processor.py     # AI processing functionality
└── context_files/       # Context files for AI prompts
```

## Development

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


