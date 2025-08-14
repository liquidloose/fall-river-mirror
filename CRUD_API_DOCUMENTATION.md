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
