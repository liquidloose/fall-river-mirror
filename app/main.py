# Standard library imports
from datetime import datetime
from enum import Enum
import logging
import os
from typing import Dict, Any, List, Optional
from app.data.enum_manager import DatabaseSync

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Third-party imports
from fastapi import APIRouter, FastAPI, HTTPException, status, Body
from fastapi.responses import JSONResponse

# Local imports
from app import TranscriptManager, ArticleGenerator
from app.writing_department.ai_journalists.aurelius_stone import AureliusStone
from app.writing_department.writing_tools.xai_processor import XAIProcessor
from app.data.enum_classes import (
    ArticleType,
    Journalist,
    Tone,
    UpdateArticleRequest,
    PartialUpdateRequest,
)
from app.data.create_database import Database
from app.data.journalist_manager import JournalistManager
from app.data.video_queue_manager import VideoQueueManager

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
transcript_manager = TranscriptManager(database)
article_generator = ArticleGenerator()

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


@app.get("/transcript/fetch/{youtube_id}", response_model=None)
def get_transcript_endpoint(
    youtube_id: str = "iGi8ymCBzhw",
) -> Dict[str, Any] | JSONResponse:

    logger.info(f"Fetching transcript for YouTube ID {youtube_id}")
    """
    Endpoint to fetch YouTube video transcripts.
    First checks database cache, then fetches from YouTube if not found and
    stores it in the database.

    Args:
        youtube_id (str): YouTube video ID (default: "VjaU4DAxP6s")

    Returns:
        Dict[str, Any] | JSONResponse: YouTube transcript data or error response
    """
    return transcript_manager.get_transcript(youtube_id)


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
    return "youtube_crawler.crawl_video(video_id)"


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
    article_type: Optional[ArticleType] = None,
    tone: Optional[Tone] = None,
    committee: Optional[str] = None,
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


@app.post("/article/generate/{journalist}/{tone}/{article_type}/{transcript_id}")
def generate_article_from_strings(
    journalist: Journalist,
    tone: Tone,
    article_type: ArticleType,
    transcript_id: int,
):
    """
    Generate article using string parameters instead of enums.
    Useful for automated calls or external integrations.
    """
    try:
        # Map string parameters to enums
        journalist_enum = None
        tone_enum = None
        article_type_enum = None

        # Map journalist string to enum
        try:
            journalist_enum = Journalist(journalist)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid journalist '{journalist}'. Valid options: {[j.value for j in Journalist]}",
            )

        # Map tone string to enum
        try:
            tone_enum = Tone(tone)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tone '{tone}'. Valid options: {[t.value for t in Tone]}",
            )

        # Map article_type string to enum
        try:
            article_type_enum = ArticleType(article_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid article_type '{article_type}'. Valid options: {[c.value for c in ArticleType]}",
            )

        # Fetch transcript content from database
        if not database:
            raise HTTPException(status_code=500, detail="Database not available")

        transcript_data = database.get_transcript_by_id(int(transcript_id))
        if not transcript_data:
            raise HTTPException(
                status_code=404, detail=f"No transcript found with ID {transcript_id}"
            )

        # Extract content from transcript data (content is at index 3)
        transcript_content = transcript_data[3]

        journalist_instance = AureliusStone()

        base_context = journalist_instance.load_context(
            tone=tone_enum, article_type=article_type_enum
        )

        # Concatenate transcript content with the context
        full_context = (
            f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
        )

        # Generate article with transcript content (no additional user context for automated calls)
        article_result = journalist_instance.generate_article(full_context, "")

        # TODO: Write article_content to database using transcript_id
        # Get journalist ID from database
        journalist_id = journalist_manager.get_journalist(aurelius.FULL_NAME)["id"]
        # Get metadata from transcript
        committee = transcript_data[1]  # committee at index 1
        youtube_id = transcript_data[2]  # youtube_id at index 2

        # Save article to database
        database.add_article(
            committee=committee,
            youtube_id=youtube_id,
            journalist_id=journalist_id,
            content=article_result["content"],
            transcript_id=transcript_id,
            date=datetime.now().isoformat(),
            article_type=article_type.value,
            tone=tone.value,
            title=article_result.get("title", "Untitled Article"),
        )

        logger.info(
            f"Article generated successfully by {journalist_instance.NAME} using transcript ID {transcript_id}"
        )
        return {
            "journalist": journalist_instance.NAME,
            "context": full_context,
            "title": (
                article_result.get("title", "Untitled Article")
                if isinstance(article_result, dict)
                else "Untitled Article"
            ),
            "content": (
                article_result.get("content", article_result)
                if isinstance(article_result, dict)
                else article_result
            ),
            "transcript_id": int(transcript_id),
            "transcript_content_length": len(transcript_content),
        }
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate article: {str(e)}"
        )


@app.post("/article/create/manually")
def generate_article(
    additional_context: str = "",
    journalist: Journalist = Journalist.AURELIUS_STONE,  # This creates the dropdown
    tone: Optional[Tone] = None,
    article_type: Optional[ArticleType] = None,
) -> Dict[str, Any]:
    try:
        # Hardcoded article ID of 1
        article_id = 1

        # Fetch transcript content from database
        if not database:
            raise HTTPException(status_code=500, detail="Database not available")

        transcript_data = database.get_transcript_by_id(article_id)
        if not transcript_data:
            raise HTTPException(
                status_code=404, detail=f"No transcript found with ID {article_id}"
            )

        # Extract content from transcript data (content is at index 3)
        transcript_content = transcript_data[3]

        journalist_instance = AureliusStone()
        base_context = journalist_instance.load_context(
            tone=tone, article_type=article_type
        )

        # Concatenate transcript content with the context
        full_context = (
            f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
        )

        # Use additional_context as user input if provided
        article_result = journalist_instance.generate_article(
            full_context, additional_context
        )

        logger.info(
            f"Article generated successfully by {journalist_instance.NAME} using transcript ID {article_id}"
        )
        return {
            "journalist": journalist_instance.NAME,
            "context": full_context,
            "article_title": (
                article_result.get("title", "Untitled Article")
                if isinstance(article_result, dict)
                else "Untitled Article"
            ),
            "article_content": (
                article_result.get("content", article_result)
                if isinstance(article_result, dict)
                else article_result
            ),
            "transcript_id": article_id,
            "transcript_content_length": len(transcript_content),
        }
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate article: {str(e)}",
        )


@app.post("/article/write/{amount_of_articles}")
async def bulk_generate_articles(
    amount_of_articles: int,
    journalist: Journalist = Journalist.AURELIUS_STONE,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.NEWS,
) -> Dict[str, Any]:
    """
    Bulk generate articles from existing transcripts.

    This endpoint:
    1. Queries the transcripts table for existing transcripts
    2. Generates articles from each transcript using the specified journalist, tone, and article type
    3. Saves all articles to the database

    Args:
        amount_of_articles: Number of articles to generate
        journalist: Journalist to write the articles (default: Aurelius Stone)
        tone: Writing tone for all articles (default: professional)
        article_type: Type of article to generate (default: news)

    Returns:
        Dict containing:
            - articles_generated: Number of articles successfully created
            - articles_failed: Number of articles that failed
            - results: List of results for each article

    Raises:
        HTTPException: If database not available or processing fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        logger.info(
            f"Starting bulk article generation: {amount_of_articles} articles, "
            f"journalist={journalist.value}, tone={tone.value}, type={article_type.value}"
        )

        # Query transcripts table for existing transcripts
        cursor = database.cursor
        cursor.execute(
            """SELECT id, committee, youtube_id, content 
               FROM transcripts 
               LIMIT ?""",
            (amount_of_articles,),
        )
        transcripts = cursor.fetchall()

        if not transcripts:
            return {
                "success": False,
                "message": "No transcripts found in database",
                "articles_generated": 0,
                "articles_failed": 0,
                "results": [],
            }

        logger.info(f"Found {len(transcripts)} transcripts to process")

        results = []
        articles_generated = 0
        articles_failed = 0

        # Get journalist instance and ID
        journalist_instance = AureliusStone()
        journalist_id = journalist_manager.get_journalist(aurelius.FULL_NAME)["id"]

        # Process each transcript
        for row in transcripts:
            # Extract transcript data from query
            transcript_id = row[0]
            committee = row[1]
            youtube_id = row[2]
            transcript_content = row[3]

            try:
                logger.info(
                    f"Processing transcript ID {transcript_id} (video {youtube_id})"
                )

                # Generate article
                logger.info(f"Generating article for transcript ID {transcript_id}")

                base_context = journalist_instance.load_context(
                    tone=tone, article_type=article_type
                )

                full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"

                article_result = journalist_instance.generate_article(full_context, "")

                # Save article to database
                database.add_article(
                    committee=committee,
                    youtube_id=youtube_id,
                    journalist_id=journalist_id,
                    content=article_result["content"],
                    transcript_id=transcript_id,
                    date=datetime.now().isoformat(),
                    article_type=article_type.value,
                    tone=tone.value,
                    title=article_result.get("title", "Untitled Article"),
                )

                articles_generated += 1
                results.append(
                    {
                        "youtube_id": youtube_id,
                        "transcript_id": transcript_id,
                        "status": "success",
                        "title": article_result.get("title", "Untitled Article"),
                    }
                )

                logger.info(f"Successfully generated article for {youtube_id}")

            except Exception as e:
                articles_failed += 1
                error_msg = str(e)
                results.append(
                    {"youtube_id": youtube_id, "status": "failed", "error": error_msg}
                )
                logger.error(
                    f"Failed to generate article for {youtube_id}: {error_msg}"
                )

        logger.info(
            f"Bulk generation complete: {articles_generated} succeeded, {articles_failed} failed"
        )

        return {
            "success": True,
            "message": f"Processed {len(transcripts)} transcripts",
            "articles_generated": articles_generated,
            "articles_failed": articles_failed,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk article generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk article generation failed: {str(e)}",
        )


@app.post("/queue/build")
async def build_video_queue(
    channel_url: str = Body(...),
    limit: int = Body(0),
) -> Dict[str, Any]:
    """
    Build the video queue by discovering videos from a YouTube channel using YouTube API.

    This endpoint:
    1. Gets all existing youtube_ids from the transcripts table
    2. Fetches video IDs from YouTube channel using YouTube Data API v3
    3. Compares and adds only new videos to the video_queue

    Requires YOUTUBE_API_KEY environment variable to be set.
    Get a free API key at: https://console.cloud.google.com/apis/credentials

    Args:
        channel_url: URL of the YouTube channel (@handle, /channel/ID, or /c/custom)
        limit: Maximum number of videos to process (default: 0 = all videos)

    Returns:
        Dict containing queue building results:
            - total_discovered: Number of videos found on YouTube
            - already_exists: Number of videos that already have transcripts
            - newly_queued: Number of videos added to queue
            - skipped: Number of videos skipped
            - failed: Number of videos that failed to process
            - youtube_ids: List of all discovered video IDs

    Raises:
        HTTPException: If database not available, API key missing, or API request fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Use async context manager
        async with VideoQueueManager(database) as queue_manager:
            # Execute queue building
            logger.info(f"Building queue from {channel_url} with limit {limit} ")
            results = await queue_manager.queue_new_videos(
                channel_url,
                limit,
            )

            logger.info(f"Queue building complete: {results}")
            return {
                "success": True,
                "message": f"Queue built successfully from {channel_url}",
                "results": results,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build video queue: {str(e)}",
        )


@app.get("/queue/stats")
def get_queue_stats() -> Dict[str, Any]:
    """
    Get statistics about the current video queue.

    Returns:
        Dict containing queue statistics:
            - total: Total videos in queue
            - transcript_available: Videos with transcripts available
            - pending: Videos without transcripts
            - errors: Videos with error messages

    Raises:
        HTTPException: If database not available
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Initialize VideoQueueManager (no browser needed for stats)
        queue_manager = VideoQueueManager(database)

        try:
            stats = queue_manager.get_queue_stats()
            return {
                "success": True,
                "stats": stats,
            }
        finally:
            queue_manager.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get queue stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue stats: {str(e)}",
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
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
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
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
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
