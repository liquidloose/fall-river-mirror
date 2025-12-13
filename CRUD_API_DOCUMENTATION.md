# CRUD API Documentation

This document describes the CRUD (Create, Read, Update, Delete) operations available for the Articles API.

## Overview

The Articles API provides full CRUD functionality for managing articles, including:
- **Create**: Generate new articles with AI processing
- **Read**: Retrieve articles with filtering and pagination
- **Update**: Modify existing articles (full and partial updates)
- **Delete**: Remove articles from the system

## Base URL

```
http://localhost:8000
```

---

## Article Generation Pipeline

This section describes the complete order of operations to go from a YouTube channel → fully generated articles with bullet points and featured images.

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ARTICLE GENERATION PIPELINE                          │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │  YouTube Channel │
                              └────────┬─────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  1. BUILD QUEUE     │
                            │  POST /queue/build  │
                            └──────────┬──────────┘
                                       │
                              ┌────────▼────────┐
                              │  video_queue    │
                              │  (youtube_ids)  │
                              └────────┬────────┘
                                       │
                       ┌───────────────▼───────────────┐
                       │  2. FETCH TRANSCRIPTS         │
                       │  POST /transcript/fetch/{n}   │
                       └───────────────┬───────────────┘
                                       │
                             ┌─────────▼─────────┐
                             │   transcripts     │
                             │ (youtube captions)│
                             └─────────┬─────────┘
                                       │
                       ┌───────────────▼───────────────┐
                       │  3. GENERATE ARTICLES         │
                       │  POST /article/write/{n}      │
                       └───────────────┬───────────────┘
                                       │
                             ┌─────────▼─────────┐
                             │    articles       │
                             │ (HTML content)    │
                             └─────────┬─────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │  4. GENERATE BULLET POINTS             │
                  │  POST /bullet-points/generate/batch/{n}│
                  └────────────────────┬───────────────────┘
                                       │
                             ┌─────────▼─────────┐
                             │    articles       │
                             │ + bullet_points   │
                             └─────────┬─────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │  5. GENERATE FEATURED IMAGES           │
                  │  POST /image/generate/batch/{artist}/{n}│
                  └────────────────────┬───────────────────┘
                                       │
                              ┌────────▼────────┐
                              │      art        │
                              │ (featured img)  │
                              └─────────────────┘
```

### Step-by-Step Breakdown

#### Step 1: Build Video Queue

```http
POST /queue/build?limit=10
```

- Uses YouTube Data API to discover videos from your channel (`DEFAULT_YOUTUBE_CHANNEL_URL` env var)
- Populates `video_queue` table with youtube_ids
- Tracks which videos have transcripts available
- Automatically adjusts limit based on existing transcripts/queue size

#### Step 2: Fetch Transcripts

```http
POST /transcript/fetch/10
```

- Pulls videos from `video_queue`
- Fetches captions via YouTube Transcript API (falls back to Whisper if unavailable)
- Stores transcript content in `transcripts` table
- Removes processed videos from queue
- Rate-limited to 1 second between requests

#### Step 3: Generate Articles

```http
POST /article/write/10?journalist=aurelius_stone&tone=professional&article_type=news
```

- Loads transcripts from database
- **Journalist Context Assembly** (`BaseJournalist.load_context()`):
  - Tone context file (e.g., `professional.txt`)
  - Article type context file (e.g., `news.txt`)
  - Slant context file (journalist's political slant)
  - Style context file (journalist's writing style)
- **Article Generation** (`BaseJournalist.generate_article()`):
  - Builds system prompt with journalist personality
  - Calls xAI/Grok API with context + transcript
  - Returns HTML-formatted article content
- Saves to `articles` table with metadata

#### Step 4: Generate Bullet Points

```http
POST /bullet-points/generate/batch/10
```

- Queries articles without `bullet_points`
- **Bullet Point Generation** (`BaseJournalist.generate_bullet_points()`):
  - Loads `bullet-point-summary` article type context
  - Sends article content to xAI API
  - Returns concise bullet summary (max 850 chars)
  - Includes citizen concerns/community feedback if present
- Updates `articles.bullet_points` column

#### Step 5: Generate Featured Images

```http
POST /image/generate/batch/spectra_veritas/10
```

- Queries articles WITH `bullet_points` but WITHOUT linked `art`
- **Snippet Generation** (`BaseArtist.generate_snippet()`):
  - Condenses bullet points to ~250 characters
  - Focuses on visual elements and mood
- **Image Generation** (`BaseArtist.generate_image()`):
  - Randomizes artistic traits per image:
    - **Medium**: oil painting, digital art, watercolor, etc.
    - **Aesthetic**: minimalist, baroque, surrealist, etc.
    - **Style**: impressionist, photorealistic, abstract, etc.
  - Builds prompt with title + snippet + style requirements
  - Calls OpenAI gpt-image-1 (or xAI grok-2-image)
- Saves to `art` table with `article_id` foreign key

### Data Flow Summary

| Step | Input | Output | Key Function |
|------|-------|--------|--------------|
| 1 | YouTube channel URL | `video_queue` rows | `VideoQueueManager.queue_new_videos()` |
| 2 | `video_queue` | `transcripts` rows | `TranscriptManager.get_transcript()` |
| 3 | `transcripts.content` | `articles` rows | `BaseJournalist.generate_article()` |
| 4 | `articles.content` | `articles.bullet_points` | `BaseJournalist.generate_bullet_points()` |
| 5 | `articles.bullet_points` | `art` rows | `BaseArtist.generate_image()` |

### Quick Run (All Steps)

```bash
# 1. Build queue (discovers videos from YouTube channel)
curl -X POST "http://localhost:8001/queue/build?limit=5"

# 2. Fetch transcripts (downloads captions for queued videos)
curl -X POST "http://localhost:8001/transcript/fetch/5"

# 3. Generate articles (AI writes articles from transcripts)
curl -X POST "http://localhost:8001/article/write/5"

# 4. Generate bullet points (summarizes articles)
curl -X POST "http://localhost:8001/bullet-points/generate/batch/5"

# 5. Generate images (creates featured images from bullet points)
curl -X POST "http://localhost:8001/image/generate/batch/spectra_veritas/5"
```

### Performance Notes

- **Queue Building**: ~1-2 seconds (YouTube API call)
- **Transcript Fetch**: ~1-2 seconds per video (rate limited)
- **Article Generation**: ~5-15 seconds per article (LLM inference)
- **Bullet Points**: ~2-5 seconds per article (LLM inference)
- **Image Generation**: ~10-30 seconds per image (image model inference)

**Estimated Total Time for 5 Articles**: ~3-5 minutes

---

## Endpoints

### 1. Create Article

**POST** `/articles/`

Creates a new article with AI-generated content.

**Request Body:**
```json
{
    "context": "The base context for the article",
    "prompt": "The user's specific writing prompt",
    "article_type": "SUMMARY",
    "tone": "PROFESSIONAL",
    "committee": "PLANNING_BOARD"
}
```

**Response (201 Created):**
```json
{
    "message": "Article created successfully",
    "article_id": "1",
    "article": {
        "id": "1",
        "context": "The base context for the article",
        "prompt": "The user's specific writing prompt",
        "article_type": "SUMMARY",
        "tone": "PROFESSIONAL",
        "committee": "PLANNING_BOARD",
        "content": "AI-generated article content...",
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T12:00:00"
    }
}
```

### 2. Read All Articles

**GET** `/articles/`

Retrieves all articles with optional filtering and pagination.

**Query Parameters:**
- `skip` (optional): Number of articles to skip (default: 0)
- `limit` (optional): Maximum number of articles to return (default: 100)
- `article_type` (optional): Filter by article type
- `tone` (optional): Filter by tone
- `committee` (optional): Filter by committee

**Examples:**
```
GET /articles/
GET /articles/?limit=10
GET /articles/?article_type=SUMMARY&tone=PROFESSIONAL
GET /articles/?skip=20&limit=10
```

**Response (200 OK):**
```json
[
    {
        "id": "1",
        "context": "Article context...",
        "prompt": "Article prompt...",
        "article_type": "SUMMARY",
        "tone": "PROFESSIONAL",
        "committee": "PLANNING_BOARD",
        "content": "Article content...",
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T12:00:00"
    }
]
```

### 3. Read Single Article

**GET** `/articles/{article_id}`

Retrieves a specific article by ID.

**Path Parameters:**
- `article_id`: The unique identifier of the article

**Response (200 OK):**
```json
{
    "id": "1",
    "context": "Article context...",
    "prompt": "Article prompt...",
    "article_type": "SUMMARY",
    "tone": "PROFESSIONAL",
    "committee": "PLANNING_BOARD",
    "content": "Article content...",
    "created_at": "2024-01-01T12:00:00",
    "updated_at": "2024-01-01T12:00:00"
}
```

**Response (404 Not Found):**
```json
{
    "detail": "Article with ID 999 not found"
}
```

### 4. Update Article (Full Update)

**PUT** `/articles/{article_id}`

Updates an existing article with new values. All fields are optional - only provided fields will be updated.

**Path Parameters:**
- `article_id`: The unique identifier of the article

**Request Body:**
```json
{
    "context": "Updated context",
    "tone": "FRIENDLY"
}
```

**Response (200 OK):**
```json
{
    "message": "Article updated successfully",
    "article": {
        "id": "1",
        "context": "Updated context",
        "prompt": "Original prompt...",
        "article_type": "SUMMARY",
        "tone": "FRIENDLY",
        "committee": "PLANNING_BOARD",
        "content": "Updated AI-generated content...",
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T13:00:00"
    }
}
```

### 5. Partial Update Article

**PATCH** `/articles/{article_id}`

Partially updates an existing article. Only the provided fields will be updated.

**Path Parameters:**
- `article_id`: The unique identifier of the article

**Request Body:**
```json
{
    "prompt": "Updated prompt only"
}
```

**Response (200 OK):**
```json
{
    "message": "Article partially updated successfully",
    "article": {
        "id": "1",
        "context": "Original context...",
        "prompt": "Updated prompt only",
        "article_type": "SUMMARY",
        "tone": "PROFESSIONAL",
        "committee": "PLANNING_BOARD",
        "content": "Original content...",
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T13:00:00"
    }
}
```

### 6. Delete Article

**DELETE** `/articles/{article_id}`

Deletes an article from the system.

**Path Parameters:**
- `article_id`: The unique identifier of the article

**Response (204 No Content):**
No content returned on successful deletion.

**Response (404 Not Found):**
```json
{
    "detail": "Article with ID 999 not found"
}
```

## Data Types

### ArticleType
- `SUMMARY`: Summary article
- `OP_ED`: Opinion/Editorial article

### Tone
- `FRIENDLY`: Friendly writing style
- `PROFESSIONAL`: Professional writing style
- `CASUAL`: Casual writing style
- `FORMAL`: Formal writing style

### Committee
- `PLANNING_BOARD`: Planning board committee

## Error Handling

All endpoints return appropriate HTTP status codes:

- **200 OK**: Successful operation
- **201 Created**: Resource created successfully
- **204 No Content**: Resource deleted successfully
- **400 Bad Request**: Invalid request data
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Server error

Error responses include a `detail` field with error information:

```json
{
    "detail": "Error message describing what went wrong"
}
```

## Testing

Use the provided test script to verify all CRUD operations:

```bash
python test_crud_endpoints.py
```

Make sure your FastAPI server is running first:

```bash
uvicorn app.main:app --reload
```

## Best Practices

1. **Use POST for creation**: Always use POST to create new resources
2. **Use PUT for full updates**: Use PUT when you want to replace the entire resource
3. **Use PATCH for partial updates**: Use PATCH when updating only specific fields
4. **Handle errors gracefully**: Always check response status codes
5. **Use pagination**: For large datasets, use skip/limit parameters
6. **Filter when possible**: Use query parameters to filter results

## Example Usage

### Creating an Article
```bash
curl -X POST "http://localhost:8000/articles/" \
  -H "Content-Type: application/json" \
  -d '{
    "context": "AI in healthcare",
    "prompt": "Write about AI applications in medicine",
    "article_type": "SUMMARY",
    "tone": "PROFESSIONAL",
    "committee": "PLANNING_BOARD"
  }'
```

### Retrieving Articles with Filters
```bash
curl "http://localhost:8000/articles/?article_type=SUMMARY&tone=PROFESSIONAL&limit=5"
```

### Updating an Article
```bash
curl -X PUT "http://localhost:8000/articles/1" \
  -H "Content-Type: application/json" \
  -d '{
    "tone": "FRIENDLY"
  }'
```

### Deleting an Article
```bash
curl -X DELETE "http://localhost:8000/articles/1"
```

## Notes

- The current implementation uses in-memory storage for demonstration purposes
- In production, replace the in-memory storage with actual database operations
- The API automatically regenerates AI content when core parameters are updated
- All timestamps are in ISO 8601 format
- The API includes comprehensive logging for debugging and monitoring
