# Standard library imports
from datetime import datetime
from enum import Enum
import logging
import os
from typing import Dict, Any, List, Optional
from app.data.db_sync import DatabaseSync

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Third-party imports
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

# Local imports
from app import TranscriptManager, ArticleGenerator, YouTubeCrawler
from app.ai_journalists.aurelius_stone import AureliusStone
from app.ai.xai_processor import XAIProcessor
from app.data.data_classes import (
    Category,
    Committee,
    Journalist,
    Tone,
    UpdateArticleRequest,
    PartialUpdateRequest,
)
from app.data.database import Database
from app.data.journalist_manager import JournalistManager

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
    database = Database("app/data/fr-mirror")
    logger.info("Database initialized successfully in main.py")
except Exception as e:
    logger.error(f"Failed to initialize database in main.py: {str(e)}")
    database = None

# Initialize database sync and run it
if database:
    db_sync = DatabaseSync(database)
    db_sync.sync_all_enums()
    logger.info(f"Database sync completed: {db_sync}")

    # Initialize journalists as proper entities
    journalist_manager = JournalistManager(database)
    aurelius = AureliusStone()

    # Create/update Aurelius Stone with bio and description
    journalist_manager.upsert_journalist(
        full_name=aurelius.FULL_NAME,
        first_name=aurelius.FIRST_NAME,
        last_name=aurelius.LAST_NAME,
        bio=aurelius.get_bio(),
        description=aurelius.get_description(),
    )
    logger.info("Journalist initialization completed")

# Initialize FastAPI application and XAI processor
app = FastAPI(
    title="Article Generation API",
    description="API for generating articles using AI processing",
    version="1.0.0",
)

xai_processor = XAIProcessor()
logger.info("FastAPI app initialized!")

# Create class instances once at startup
transcript_manager = TranscriptManager(Committee.BOARD_OF_HEALTH, database)
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
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/transcript/fetch/{committee}/{youtube_id=iGi8ymCBzhw}", response_model=None)
def get_transcript_endpoint(
    committee: Committee,
    youtube_id: str = "iGi8ymCBzhw",
) -> Dict[str, Any] | JSONResponse:

    logger.info(
        f"Fetching transcript for committee {committee} and YouTube ID {youtube_id}"
    )
    """
    Endpoint to fetch YouTube video transcripts.
    First checks database cache, then fetches from YouTube if not found and
    stores it in the database.

    Args:
        youtube_id (str): YouTube video ID (default: "VjaU4DAxP6s")

    Returns:
        Dict[str, Any] | JSONResponse: YouTube transcript data or error response
    """
    return transcript_manager.get_transcript(committee, youtube_id)


@app.delete("/transcript/delete/{transcript_id}")
def delete_transcript_endpoint(transcript_id: int) -> Dict[str, Any]:
    """
    Delete a transcript by its ID.

    Args:
        transcript_id: The ID of the transcript to delete

    Returns:
        Dict containing success status and message

    Raises:
        HTTPException: If transcript not found or database operation fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        success = database.delete_transcript_by_id(transcript_id)

        if success:
            logger.info(f"Successfully deleted transcript with ID {transcript_id}")
            return {
                "success": True,
                "message": f"Transcript with ID {transcript_id} deleted successfully",
                "transcript_id": transcript_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transcript with ID {transcript_id} not found",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete transcript {transcript_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete transcript: {str(e)}",
        )


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
            "message": f"There are {count} articles in the database",
        }

    except Exception as e:
        logger.error(f"Failed to get article count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get article count: {str(e)}",
        )


@app.get("/articles/", response_model=List[Dict[str, Any]])
async def get_all_articles(
    skip: int = 0,
    limit: int = 100,
    article_type: Optional[Category] = None,
    tone: Optional[Tone] = None,
    committee: Optional[Committee] = None,
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
        articles = articles[skip : skip + limit]

        logger.info(f"Retrieved {len(articles)} articles")
        return articles

    except Exception as e:
        logger.error(f"Failed to retrieve articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}",
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
                detail=f"Article with ID {article_id} not found",
            )

        logger.info(f"Retrieved article with ID: {article_id}")
        return articles_db[article_id]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve article: {str(e)}",
        )


@app.get("/journalist/{journalist_name}")
def get_journalist_profile(journalist_name: Journalist):
    """
    Get complete profile information for a specific journalist.
    Returns bio, description, writing style, slant, and all other attributes.
    """
    try:
        # Map journalist enum values to their classes
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
        }

        # Get the journalist class
        journalist_class = journalist_classes.get(journalist_name)
        if not journalist_class:
            available_journalists = [j.value for j in Journalist]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journalist '{journalist_name.value}' not found. Available journalists: {available_journalists}",
            )

        # Create journalist instance
        journalist = journalist_class()

        # Get complete profile information
        profile = journalist.get_full_profile()

        # Add additional context information
        profile.update(
            {
                "default_tone": journalist.DEFAULT_TONE.value,
                "default_article_type": journalist.DEFAULT_ARTICLE_TYPE.value,
                "slant": journalist.SLANT,
                "style": journalist.STYLE,
                "first_name": journalist.FIRST_NAME,
                "last_name": journalist.LAST_NAME,
                "full_name": journalist.FULL_NAME,
            }
        )

        # Load context files for slant, style, and tone
        try:
            slant = journalist._load_attribute_context(
                "./app/context_files", "slant", journalist.SLANT
            )
            style = journalist._load_attribute_context(
                "./app/context_files", "style", journalist.STYLE
            )
            tone = journalist._load_attribute_context(
                "./app/context_files", "tone", journalist.DEFAULT_TONE.value
            )

            profile.update(
                {
                    "slant": slant,
                    "style": style,
                    "tone": tone,
                }
            )
        except Exception as e:
            logger.warning(f"Could not load context files: {str(e)}")
            profile.update(
                {
                    "slant": "Context file not available",
                    "style": "Context file not available",
                    "tone": "Context file not available",
                }
            )

        logger.info(f"Retrieved complete profile for {journalist.FULL_NAME}")
        return profile

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve journalist profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve journalist profile: {str(e)}",
        )


# ===== POST ENDPOINTS =====


@app.post("/article/generate")
def generate_article(
    content: str = "",
    journalist: Journalist = Journalist.AURELIUS_STONE,  # This creates the dropdown
    tone: Optional[Tone] = None,
    article_type: Optional[Category] = None,
):
    try:
        journalist = AureliusStone()
        context = journalist.load_context(tone=tone, article_type=article_type)
        article_content = journalist.generate_article(context, content)
        logger.info(f"Article generated successfully by {journalist.NAME}")
        return {
            "journalist": journalist.NAME,
            "context": context,
            "generated_article": article_content,
        }
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate article: {str(e)}",
        )


# ===== PUT ENDPOINTS =====


@app.put("/articles/{article_id}")
async def update_article(
    article_id: str, request: UpdateArticleRequest
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
                detail=f"Article with ID {article_id} not found",
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
        if any(
            [
                request.context,
                request.prompt,
                request.article_type,
                request.tone,
                request.committee,
            ]
        ):
            try:
                new_content = article_generator.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=Category(article["article_type"]),
                    tone=Tone(article["tone"]),
                    committee=Committee(article["committee"]),
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")

        article["updated_at"] = datetime.now().isoformat()

        logger.info(f"Article {article_id} updated successfully")
        return {"message": "Article updated successfully", "article": article}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update article: {str(e)}",
        )


# ===== PATCH ENDPOINTS =====


@app.patch("/articles/{article_id}")
async def partial_update_article(
    article_id: str, request: PartialUpdateRequest
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
                detail=f"Article with ID {article_id} not found",
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
        if any(
            [
                request.context,
                request.prompt,
                request.article_type,
                request.tone,
                request.committee,
            ]
        ):
            try:
                new_content = article_generator.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=Category(article["article_type"]),
                    tone=Tone(article["tone"]),
                    committee=Committee(article["committee"]),
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")

        article["updated_at"] = datetime.now().isoformat()

        logger.info(f"Article {article_id} partially updated successfully")
        return {"message": "Article partially updated successfully", "article": article}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to partially update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to partially update article: {str(e)}",
        )
