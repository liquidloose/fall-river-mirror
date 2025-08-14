# Standard library imports
from datetime import datetime
from enum import Enum
import logging
from typing import Dict, Any, List, Optional

# Third-party imports
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

# Local imports
from app import TranscriptManager, ArticleGenerator, YouTubeCrawler
from .xai_processor import XAIProcessor 
from .data_classes import ArticleType, Committee, Tone, GenerateArticleRequest, CreateArticleRequest, UpdateArticleRequest, PartialUpdateRequest
from .database import Database

# Configure logging with both console and file output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler("app.log"),  # File output
    ],
)
logger = logging.getLogger(__name__)

# Initialize database instance at the top level
try:
    database = Database("fr-mirror")
    logger.info("Database initialized successfully in main.py")
except Exception as e:
    logger.error(f"Failed to initialize database in main.py: {str(e)}")
    database = None

# Initialize FastAPI application and XAI processor
app = FastAPI(
    title="Article Generation API",
    description="API for generating articles using AI processing",
    version="1.0.0"
)

xai_processor = XAIProcessor()
logger.info("FastAPI app initialized!")

# Create class instances once at startup
transcript_manager = TranscriptManager(database)
article_generator = ArticleGenerator()
youtube_crawler = YouTubeCrawler(database)

# In-memory storage for demo purposes (replace with actual database operations)
articles_db = {}

# ===== GET ENDPOINTS =====

@app.get("/")
def health_check() -> Dict[str, str]:
    """
    Health check endpoint to verify the server is running.
    
    Returns:
        dict: Status message indicating server is operational
    """
    logger.info("Health check endpoint called!")
    
    # Add database status to health check
    db_status = "connected" if database and database.is_connected else "disconnected"
    
    return {
        "status": "ok", 
        "message": "Server is running",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/transcript/{youtube_id=VjaU4DAxP6s}", response_model=None)
def get_transcript_endpoint(youtube_id: str = "VjaU4DAxP6s") -> Dict[str, Any] | JSONResponse:
    """
    Endpoint to fetch YouTube video transcripts.
    First checks database cache, then fetches from YouTube if not found.
    
    Args:
        youtube_id (str): YouTube video ID (default: "VjaU4DAxP6s")
    
    Returns:
        Dict[str, Any] | JSONResponse: YouTube transcript data or error response
    """
    return transcript_manager.get_transcript(youtube_id)

@app.get("/yt_crawler/{video_id}", response_model=None)
async def yt_crawler_endpoint(video_id: str) -> Dict[str, Any] | JSONResponse:
    """
    YouTube crawler endpoint that crawls down the archive video page and records information about each video.
    
    This endpoint demonstrates how to make internal calls to other endpoints
    in the same FastAPI application.
    
    Args:
        video_id (str): YouTube video ID to crawl
    
    Returns:
        Dict[str, Any] | JSONResponse: Combined data from transcript and processing
    """
    return youtube_crawler.crawl_video(video_id)

@app.get("/articles/count")
async def get_article_count() -> Dict[str, Any]:
    """
    Get the total count of articles.
    
    Returns:
        Dict containing the article count
    """
    try:
        count = len(articles_db)
        logger.info(f"Article count: {count}")
        return {
            "total_articles": count,
            "message": f"There are {count} articles in the database"
        }
        
    except Exception as e:
        logger.error(f"Failed to get article count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get article count: {str(e)}"
        )

@app.get("/articles/", response_model=List[Dict[str, Any]])
async def get_all_articles(
    skip: int = 0,
    limit: int = 100,
    article_type: Optional[ArticleType] = None,
    tone: Optional[Tone] = None,
    committee: Optional[Committee] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve all articles with optional filtering.
    
    Args:
        skip: Number of articles to skip (for pagination)
        limit: Maximum number of articles to return
        article_type: Filter by article type
        tone: Filter by tone
        committee: Filter by committee
    
    Returns:
        List of articles matching the criteria
    """
    try:
        articles = list(articles_db.values())
        
        # Apply filters
        if article_type:
            articles = [a for a in articles if a["article_type"] == article_type.value]
        if tone:
            articles = [a for a in articles if a["tone"] == tone.value]
        if committee:
            articles = [a for a in articles if a["committee"] == committee.value]
        
        # Apply pagination
        articles = articles[skip:skip + limit]
        
        logger.info(f"Retrieved {len(articles)} articles")
        return articles
        
    except Exception as e:
        logger.error(f"Failed to retrieve articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )

@app.get("/articles/{article_id}", response_model=Dict[str, Any])
async def get_article(article_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific article by ID.
    
    Args:
        article_id: The unique identifier of the article
    
    Returns:
        The article data
    """
    try:
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found"
            )
        
        logger.info(f"Retrieved article with ID: {article_id}")
        return articles_db[article_id]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve article: {str(e)}"
        )

# ===== POST ENDPOINTS =====

@app.post("/articles/generate/{context}/{prompt}/{article_type}/{tone}/{committee}", response_model=None)
def generate_article_endpoint(
    context: str,
    prompt: str,
    article_type: ArticleType,
    tone: Tone,
    committee: Committee
) -> Dict[str, Any] | JSONResponse:
    """
    Generate article content based on context and parameters.
    
    Args:
        context: The base context for the article
        prompt: The user's specific writing prompt
        article_type: Type of article to generate
        tone: Writing tone to use
        committee: Committee type for the article
    
    Returns:
        Dict[str, Any] | JSONResponse: Generated article content from the XAI processor or error response
    """
    return article_generator.write_article(
        context=context,
        prompt=prompt,
        article_type=article_type,
        tone=tone,
        committee=committee
    )

@app.post("/articles/create", status_code=status.HTTP_201_CREATED)
async def create_article(request: CreateArticleRequest) -> Dict[str, Any]:
    """
    Create a new article.
    
    Args:
        request: The article creation request containing context, prompt, type, tone, and committee
    
    Returns:
        Dict containing the created article data
    """
    try:
        # Generate the article using ArticleGenerator
        article_content = article_generator.write_article(
            context=request.context,
            prompt=request.prompt,
            article_type=request.article_type,
            tone=request.tone,
            committee=request.committee
        )
        
        # Create article record
        article_id = str(len(articles_db) + 1)
        article_record = {
            "id": article_id,
            "context": request.context,
            "prompt": request.prompt,
            "article_type": request.article_type.value,
            "tone": request.tone.value,
            "committee": request.committee.value,
            "content": article_content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        articles_db[article_id] = article_record
        logger.info(f"Article created successfully with ID: {article_id}")
        
        return {
            "message": "Article created successfully",
            "article_id": article_id,
            "article": article_record
        }
        
    except Exception as e:
        logger.error(f"Failed to create article: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create article: {str(e)}"
        )

# ===== DELETE ENDPOINTS =====

@app.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(article_id: str):
    """
    Delete an article.
    
    Args:
        article_id: The unique identifier of the article to delete
    """
    try:
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found"
            )
        
        del articles_db[article_id]
        logger.info(f"Article {article_id} deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete article: {str(e)}"
        )

# ===== PUT ENDPOINTS =====

@app.put("/articles/{article_id}")
async def update_article(
    article_id: str,
    request: UpdateArticleRequest
) -> Dict[str, Any]:
    """
    Update an existing article (full update).
    
    Args:
        article_id: The unique identifier of the article
        request: The update request containing fields to update
    
    Returns:
        Updated article data
    """
    try:
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found"
            )
        
        article = articles_db[article_id]
        
        # Update fields if provided
        if request.context is not None:
            article["context"] = request.context
        if request.prompt is not None:
            article["prompt"] = request.prompt
        if request.article_type is not None:
            article["article_type"] = request.article_type.value
        if request.tone is not None:
            article["tone"] = request.tone.value
        if request.committee is not None:
            article["committee"] = request.committee.value
        
        # Regenerate content if any core parameters changed
        if any([request.context, request.prompt, request.article_type, request.tone, request.committee]):
            try:
                new_content = article_generator.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
                    committee=Committee(article["committee"])
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")
        
        article["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"Article {article_id} updated successfully")
        return {
            "message": "Article updated successfully",
            "article": article
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update article: {str(e)}"
        )

# ===== PATCH ENDPOINTS =====

@app.patch("/articles/{article_id}")
async def partial_update_article(
    article_id: str,
    request: PartialUpdateRequest
) -> Dict[str, Any]:
    """
    Partially update an existing article.
    
    Args:
        article_id: The unique identifier of the article
        request: The partial update request containing fields to update
    
    Returns:
        Updated article data
    """
    try:
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found"
            )
        
        article = articles_db[article_id]
        
        # Update only the provided fields
        if request.context is not None:
            article["context"] = request.context
        if request.prompt is not None:
            article["prompt"] = request.prompt
        if request.article_type is not None:
            article["article_type"] = request.article_type.value
        if request.tone is not None:
            article["tone"] = request.tone.value
        if request.committee is not None:
            article["committee"] = request.committee.value
        
        # Regenerate content if any core parameters changed
        if any([request.context, request.prompt, request.article_type, request.tone, request.committee]):
            try:
                new_content = article_generator.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
                    committee=Committee(article["committee"])
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")
        
        article["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"Article {article_id} partially updated successfully")
        return {
            "message": "Article partially updated successfully",
            "article": article
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to partially update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to partially update article: {str(e)}"
        )
