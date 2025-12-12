# Standard library imports
from datetime import datetime
from enum import Enum
import json
import logging
import os
import time
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
from fastapi.responses import JSONResponse, Response

# Local imports
from app import TranscriptManager, ArticleGenerator
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.creation_tools.xai_text_query import XAITextQuery
from app.data.enum_classes import (
    ArticleType,
    Tone,
    Journalist,
    Artist,
    ImageModel,
    CreateArticleRequest,
    UpdateArticleRequest,
    PartialUpdateRequest,
)
from app.data.create_database import Database
from app.data.journalist_manager import JournalistManager
from app.data.video_queue_manager import VideoQueueManager
from app.content_department.ai_artists.spectra_veritas import SpectraVeritas

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


@app.delete("/art/delete/{art_id}")
def delete_art_endpoint(art_id: int) -> Dict[str, Any]:
    """
    Delete an art record by its ID.

    Args:
        art_id: The ID of the art record to delete

    Returns:
        Dict containing success status and message

    Raises:
        HTTPException: If art not found or database operation fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        success = database.delete_art_by_id(art_id)

        if success:
            logger.info(f"Successfully deleted art with ID {art_id}")
            return {
                "success": True,
                "message": f"Art with ID {art_id} deleted successfully",
                "art_id": art_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Art with ID {art_id} not found",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete art {art_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete art: {str(e)}",
        )


@app.post("/transcript/fetch/{amount}")
async def bulk_fetch_transcripts(
    amount: int,
    auto_build: bool = Body(True),
) -> Dict[str, Any]:
    """
    Bulk fetch and store transcripts for queued YouTube videos.

    ## Purpose
    This endpoint processes videos from the video_queue table, fetching their transcripts
    and storing them in the database. It's designed for batch processing of multiple videos
    with built-in error handling, rate limiting, automatic queue building, and automatic queue cleanup.

    ## Workflow
    1. Check if queue has enough videos (at least `amount` videos available)
       - If insufficient and `auto_build=True`: Automatically build queue to meet requested amount
         * Uses `DEFAULT_YOUTUBE_CHANNEL_URL` environment variable
       - If insufficient and `auto_build=False`: Proceed with available videos only
    2. Query video_queue for up to `amount` videos where:
       - transcript_available = 1 (YouTube has captions available)
       - youtube_id NOT already in transcripts table (avoid duplicates)
    3. For each video in the queue:
       - Fetch transcript using TranscriptManager (tries YouTube Transcript API first, falls back to Whisper)
       - Fetch video metadata from YouTube Data API (title, duration, statistics)
       - Store transcript and metadata in transcripts table
       - On success: Remove video from queue
       - On failure: Keep video in queue, log error
    4. Apply rate limiting (1 second between requests) to avoid API throttling
    5. Return detailed results for monitoring and debugging

    ## Parameters
    - **amount** (path, required): Maximum number of transcripts to fetch from queue
      - Type: int
      - Must be positive integer
      - Example: `/transcript/fetch/10` fetches up to 10 transcripts
    
    - **auto_build** (body, optional): Enable/disable automatic queue building
      - Type: boolean (default: `True`)
      - If `True` and queue has fewer than `amount` videos, automatically builds queue from `DEFAULT_YOUTUBE_CHANNEL_URL`
      - If `False`, proceeds with whatever videos are available in queue
      - Useful to disable for manual queue control or testing

    ## Response Format

    ### Success Response (200 OK)
    ```json
    {
        "success": true,
        "message": "Processed 10 videos from queue",
        "transcripts_fetched": 8,
        "transcripts_failed": 2,
        "results": [
            {
                "youtube_id": "abc123xyz",
                "status": "success",
                "source": "youtube_api"
            },
            {
                "youtube_id": "def456uvw",
                "status": "failed",
                "error": "No transcript available"
            }
        ],
        "auto_build": {
            "triggered": true,
            "videos_added": 5,
            "channel_url": "https://www.youtube.com/@FallRiverCityCouncil"
        }
    }
    ```

    **Response Fields:**
    - `success` (bool): Overall operation success indicator
    - `message` (str): Human-readable summary
    - `transcripts_fetched` (int): Count of successfully fetched transcripts
    - `transcripts_failed` (int): Count of failed transcript fetches
    - `results` (list): Detailed per-video results
      - `youtube_id` (str): Video identifier
      - `status` (str): "success" or "failed"
      - `source` (str): Transcript source ("youtube_api" or "whisper") [success only]
      - `error` (str): Error message [failure only]
    - `auto_build` (object, optional): Auto-build information [only present if triggered]
      - `triggered` (bool): Whether auto-build was activated
      - `videos_added` (int): Number of videos added to queue
      - `channel_url` (str): Channel URL used for building

    ### Empty Queue Response (200 OK)
    ```json
    {
        "success": false,
        "message": "No videos with transcripts available in queue or all already fetched",
        "transcripts_fetched": 0,
        "transcripts_failed": 0,
        "results": []
    }
    ```

    ### Error Response (500 Internal Server Error)
    ```json
    {
        "detail": "Bulk transcript fetch failed: Database connection lost"
    }
    ```

    ## Rate Limiting
    - 1 second delay between consecutive video processing
    - Prevents YouTube API rate limit errors
    - Configurable via RATE_LIMIT_MS constant

    ## Queue Management
    - Successfully processed videos are **automatically removed** from video_queue
    - Failed videos **remain in queue** for retry in future runs
    - Videos already in transcripts table are **automatically skipped**

    ## Error Handling
    - Individual video failures don't stop the batch process
    - All errors are logged with detailed context
    - Partial success is possible (some succeed, some fail)
    - Database transactions are committed after each successful fetch

    ## Use Cases
    - **Initial bulk import**: Process large backlog of queued videos
    - **Scheduled batch jobs**: Run periodically (e.g., hourly cron job)
    - **Manual processing**: Operator-triggered fetch when new videos detected
    - **Recovery**: Reprocess failed videos after fixing issues

    ## Example Usage
    ```bash
    # Simple: Fetch 25 transcripts (uses DEFAULT_YOUTUBE_CHANNEL_URL env var, auto-build enabled)
    curl -X POST "http://localhost:8001/transcript/fetch/25"
    
    # With auto-build disabled (only fetches what's already in queue)
    curl -X POST "http://localhost:8001/transcript/fetch/25" \
      -H "Content-Type: application/json" \
      -d '{"auto_build": false}'
    
    # Fetch single transcript (useful for testing)
    curl -X POST "http://localhost:8001/transcript/fetch/1"
    ```

    ## Related Endpoints
    - POST `/queue/build` - Populate video_queue by scraping YouTube channel
    - GET `/queue/stats` - Check video_queue status before bulk fetch
    - GET `/transcript/{youtube_id}` - Fetch single transcript by ID

    ## Performance Notes
    - Processing time: ~1-2 seconds per video (due to rate limiting)
    - 10 videos ≈ 10-20 seconds total
    - 100 videos ≈ 100-200 seconds (~1.5-3 minutes)
    - Whisper fallback adds ~30-60 seconds per video (if needed)

    Args:
        amount (int): Maximum number of transcripts to fetch from queue (must be positive)
        auto_build (bool): Enable automatic queue building if insufficient videos (default: True)
            Uses DEFAULT_YOUTUBE_CHANNEL_URL environment variable for building queue.

    Returns:
        Dict[str, Any]: Response dictionary containing:
            - success (bool): Overall operation status
            - message (str): Human-readable summary
            - transcripts_fetched (int): Count of successful fetches
            - transcripts_failed (int): Count of failed fetches
            - results (List[Dict]): Per-video detailed results

    Raises:
        HTTPException (500): Database unavailable or unexpected error during processing
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        logger.info(f"Starting bulk transcript fetch for {amount} videos from queue")

        # ========================================
        # Step 1: Check Queue Size and Auto-Build if Needed
        # ========================================
        # Count available videos in queue (transcript_available = 1, not already in transcripts table)
        cursor = database.cursor
        cursor.execute(
            """SELECT COUNT(*) 
               FROM video_queue AS T1
               LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
               WHERE T1.transcript_available = 1 AND T2.youtube_id IS NULL"""
        )
        available_count = cursor.fetchone()[0]

        logger.info(
            f"Found {available_count} videos available in queue, requested {amount}"
        )

        # Track auto-build info for response
        auto_build_triggered = False
        auto_build_added = 0

        # Get default channel URL from environment
        channel_url = os.getenv("DEFAULT_YOUTUBE_CHANNEL_URL")
        if channel_url:
            logger.info(f"Using default channel URL from environment: {channel_url}")

        # If insufficient videos, auto_build enabled, and channel_url available, build more queue entries
        if available_count < amount and auto_build and channel_url:
            auto_build_triggered = True
            shortfall = amount - available_count
            logger.info(
                f"Queue has only {available_count}/{amount} videos. "
                f"Auto-building {shortfall} more from {channel_url}"
            )

            try:
                # Use async context manager to build queue
                async with VideoQueueManager(database) as queue_manager:
                    build_results = await queue_manager.queue_new_videos(
                        channel_url,
                        max_limit=shortfall,
                    )
                    auto_build_added = build_results.get("newly_queued", 0)
                    logger.info(
                        f"Auto-build complete: {auto_build_added} videos added to queue"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to auto-build queue: {str(e)}. Proceeding with available videos."
                )
        elif available_count < amount and not auto_build:
            logger.info(
                f"Queue has only {available_count}/{amount} videos. "
                f"Auto-build disabled. Proceeding with available videos."
            )
        elif available_count < amount:
            logger.warning(
                f"Queue has only {available_count}/{amount} videos. "
                f"No channel_url available (not provided and DEFAULT_YOUTUBE_CHANNEL_URL not set). "
                f"Proceeding with available videos."
            )

        # ========================================
        # Step 2: Query Available Videos from Queue
        # ========================================
        # Query video_queue for videos with transcripts available and not already in transcripts table
        cursor.execute(
            """SELECT T1.youtube_id
               FROM video_queue AS T1
               LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
               WHERE T1.transcript_available = 1 AND T2.youtube_id IS NULL
               LIMIT ?""",
            (amount,),
        )
        queue_items = cursor.fetchall()

        if not queue_items:
            return {
                "success": False,
                "message": "No videos with transcripts available in queue or all already fetched",
                "transcripts_fetched": 0,
                "transcripts_failed": 0,
                "results": [],
            }

        logger.info(f"Found {len(queue_items)} videos in queue to process")

        results = []
        transcripts_fetched = 0
        transcripts_failed = 0

        # Rate limit in milliseconds (adjust as needed)
        RATE_LIMIT_MS = 1000  # 1 second between requests

        for row in queue_items:
            youtube_id = row[0]

            try:
                logger.info(f"Fetching transcript for video {youtube_id}")
                transcript_result = transcript_manager.get_transcript(youtube_id)

                # Check if transcript_result is a JSONResponse (error) or a Dict (success)
                if isinstance(transcript_result, JSONResponse):
                    # Extract error message from JSONResponse content
                    import json

                    error_content = json.loads(transcript_result.body.decode())
                    raise Exception(
                        error_content.get(
                            "error", "Unknown error during transcript fetch"
                        )
                    )

                transcripts_fetched += 1
                results.append(
                    {
                        "youtube_id": youtube_id,
                        "status": "success",
                        "source": transcript_result.get("source"),
                    }
                )
                logger.info(f"Successfully fetched transcript for {youtube_id}")

                # Remove from queue after successful fetch
                cursor.execute(
                    "DELETE FROM video_queue WHERE youtube_id = ?", (youtube_id,)
                )
                database.conn.commit()
                logger.debug(f"Removed {youtube_id} from video_queue")

            except Exception as e:
                transcripts_failed += 1
                error_msg = str(e)
                results.append(
                    {"youtube_id": youtube_id, "status": "failed", "error": error_msg}
                )
                logger.error(
                    f"Failed to fetch transcript for {youtube_id}: {error_msg}"
                )

            # Rate limit: sleep between requests
            time.sleep(RATE_LIMIT_MS / 1000.0)

        logger.info(
            f"Bulk transcript fetch complete: {transcripts_fetched} succeeded, {transcripts_failed} failed"
        )

        response = {
            "success": True,
            "message": f"Processed {len(queue_items)} videos from queue",
            "transcripts_fetched": transcripts_fetched,
            "transcripts_failed": transcripts_failed,
            "results": results,
        }

        # Add auto-build info if it was triggered
        if auto_build_triggered:
            response["auto_build"] = {
                "triggered": True,
                "videos_added": auto_build_added,
                "channel_url": channel_url,
            }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk transcript fetch failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk transcript fetch failed: {str(e)}",
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


@app.post("/image/generate/batch/{artist_name}/{amount}")
def bulk_generate_images(
    amount: int,
    artist_name: Artist = Artist.SPECTRA_VERITAS,
    model: ImageModel = ImageModel.MINI,
) -> Dict[str, Any]:
    """
    Bulk generate images for articles that have bullet points but no existing art.

    This endpoint:
    1. Queries articles with bullet_points that don't already have art
    2. Generates images for each article using the specified artist and model
    3. Saves all images to the art table

    Args:
        amount: Maximum number of images to generate
        artist_name: AI artist to use (default: Spectra Veritas)
        model: Image model to use (default: gpt-image-1-mini)

    Returns:
        Dict containing:
            - success: Overall operation status
            - message: Human-readable summary
            - images_generated: Count of successfully created images
            - images_failed: Count of failed image generations
            - results: List of per-article results
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        logger.info(
            f"Starting bulk image generation: {amount} images, "
            f"artist={artist_name.value}, model={model.value}"
        )

        # Create artist instance (currently only Spectra Veritas is available)
        artist_instance = SpectraVeritas()

        # Query articles that have bullet_points but no existing art
        cursor = database.cursor
        cursor.execute(
            """SELECT a.id, a.title, a.bullet_points, a.transcript_id
               FROM articles a
               LEFT JOIN art ON a.id = art.article_id
               WHERE a.bullet_points IS NOT NULL 
                 AND a.bullet_points != ''
                 AND art.id IS NULL
               LIMIT ?""",
            (amount,),
        )
        articles = cursor.fetchall()

        if not articles:
            return {
                "success": True,
                "message": "No articles found that need images (all have art or lack bullet_points)",
                "images_generated": 0,
                "images_failed": 0,
                "results": [],
            }

        logger.info(f"Found {len(articles)} articles to process")

        results = []
        images_generated = 0
        images_failed = 0

        for row in articles:
            article_id = row[0]
            title = row[1]
            bullet_points = row[2]
            transcript_id = row[3]

            try:
                # Double-check this article doesn't already have art (race condition protection)
                cursor.execute(
                    "SELECT id FROM art WHERE article_id = ? LIMIT 1",
                    (article_id,),
                )
                existing_art = cursor.fetchone()
                if existing_art:
                    logger.info(
                        f"Skipping article {article_id} - already has art (ID: {existing_art[0]})"
                    )
                    results.append(
                        {
                            "article_id": article_id,
                            "status": "skipped",
                            "reason": "already has art",
                            "existing_art_id": existing_art[0],
                        }
                    )
                    continue

                logger.info(f"Generating image for article ID {article_id}: {title}")

                # Generate image
                image_result = artist_instance.generate_image(
                    title=title,
                    bullet_points=bullet_points,
                    model=model.value,
                )

                if image_result.get("error"):
                    images_failed += 1
                    results.append(
                        {
                            "article_id": article_id,
                            "status": "failed",
                            "error": image_result["error"],
                        }
                    )
                    logger.error(
                        f"Failed to generate image for article {article_id}: {image_result['error']}"
                    )
                    continue

                # Save to database if successful
                if image_result.get("image_url"):
                    import requests
                    import base64

                    image_url = image_result["image_url"]

                    # Handle base64 data URLs (from gpt-image-1)
                    if image_url.startswith("data:image"):
                        header, base64_data = image_url.split(",", 1)
                        image_data = base64.b64decode(base64_data)

                        art_id = database.add_art(
                            prompt=image_result["prompt_used"],
                            image_url=None,
                            image_data=image_data,
                            medium=image_result.get("medium"),
                            aesthetic=image_result.get("aesthetic"),
                            title=title,
                            artist_name=image_result.get("artist"),
                            snippet=image_result.get("snippet"),
                            transcript_id=transcript_id,
                            article_id=article_id,
                            model=model.value,
                        )
                    else:
                        # Handle regular URLs (from other providers)
                        response = requests.get(image_url)

                        if response.status_code == 200:
                            art_id = database.add_art(
                                prompt=image_result["prompt_used"],
                                image_url=image_url,
                                image_data=response.content,
                                medium=image_result.get("medium"),
                                aesthetic=image_result.get("aesthetic"),
                                title=title,
                                artist_name=image_result.get("artist"),
                                snippet=image_result.get("snippet"),
                                transcript_id=transcript_id,
                                article_id=article_id,
                                model=model.value,
                            )
                        else:
                            images_failed += 1
                            results.append(
                                {
                                    "article_id": article_id,
                                    "status": "failed",
                                    "error": f"Failed to download image: {response.status_code}",
                                }
                            )
                            continue

                    images_generated += 1
                    results.append(
                        {
                            "article_id": article_id,
                            "status": "success",
                            "art_id": art_id,
                            "title": title,
                        }
                    )
                    logger.info(
                        f"Successfully generated image for article {article_id} (art_id: {art_id})"
                    )
                else:
                    images_failed += 1
                    results.append(
                        {
                            "article_id": article_id,
                            "status": "failed",
                            "error": "No image URL returned",
                        }
                    )

            except Exception as e:
                images_failed += 1
                error_msg = str(e)
                results.append(
                    {"article_id": article_id, "status": "failed", "error": error_msg}
                )
                logger.error(
                    f"Failed to generate image for article {article_id}: {error_msg}"
                )

        logger.info(
            f"Bulk image generation complete: {images_generated} succeeded, {images_failed} failed"
        )

        return {
            "success": True,
            "message": f"Processed {len(articles)} articles",
            "images_generated": images_generated,
            "images_failed": images_failed,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk image generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk image generation failed: {str(e)}",
        )


@app.post("/image/generate/{artist_name}/{article_id}")
def generate_image(
    artist_name: Artist,
    article_id: int,
    model: ImageModel = ImageModel.MINI,
):
    """
    Generate an image using the xAI Aurora API.
    """
    # Map artist enum values to their classes
    artist_classes = {
        Artist.SPECTRA_VERITAS: SpectraVeritas,
    }

    # Get the artist class
    artist_class = artist_classes.get(artist_name)
    if not artist_class:
        available_artists = [a.value for a in Artist]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artist '{artist_name.value}' not found. Available artists: {available_artists}",
        )

    article = database.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID {article_id} not found",
        )

    bullet_points = article.get("bullet_points")
    if not bullet_points:
        return {
            "image_url": None,
            "error": f"Article {article_id} has no bullet points. Generate bullet points first using PATCH /article/{article_id}/bullet-points",
            "article_id": article_id,
        }

    # Create artist instance dynamically
    artist_instance = artist_class()
    image_result = artist_instance.generate_image(
        title=article["title"],
        bullet_points=bullet_points,
        model=model.value,
    )

    # Save to database if successful
    if image_result.get("image_url"):
        import requests
        import base64

        # Download the image
        image_url = image_result["image_url"]

        # Handle base64 data URLs (from gpt-image-1)
        if image_url.startswith("data:image"):
            # Extract base64 data from data URL
            # Format: data:image/png;base64,<base64_data>
            header, base64_data = image_url.split(",", 1)
            image_data = base64.b64decode(base64_data)

            art_id = database.add_art(
                prompt=image_result["prompt_used"],
                image_url=None,  # Changed from image_url - don't store the huge base64 string
                image_data=image_data,
                medium=image_result.get("medium"),
                aesthetic=image_result.get("aesthetic"),
                title=article["title"],
                artist_name=image_result.get("artist"),
                snippet=image_result.get("snippet"),
                transcript_id=article.get("transcript_id"),
                article_id=article_id,
                model=model.value,
            )
            image_result["art_id"] = art_id
        else:
            # Handle regular URLs (from other providers)
            response = requests.get(image_url)

            if response.status_code == 200:
                art_id = database.add_art(
                    prompt=image_result["prompt_used"],
                    image_url=image_url,
                    image_data=response.content,
                    medium=image_result.get("medium"),
                    aesthetic=image_result.get("aesthetic"),
                    title=article["title"],
                    artist_name=image_result.get("artist"),
                    snippet=image_result.get("snippet"),
                    transcript_id=article.get("transcript_id"),
                    article_id=article_id,
                    model=model.value,
                )
                image_result["art_id"] = art_id
            else:
                image_result["error"] = (
                    f"Failed to download image: {response.status_code}"
                )

    return image_result


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
    limit: int = 5,
    channel_url: str = os.environ.get("DEFAULT_YOUTUBE_CHANNEL_URL", ""),
) -> Dict[str, Any]:
    """
    Build the video queue by discovering videos from a YouTube channel using YouTube API.

    This endpoint intelligently adjusts the scrape limit to account for already-processed videos.
    If you request limit=10, it will scrape (current_transcript_count + 10) videos from the channel,
    ensuring you get approximately 10 NEW videos added to the queue.

    This endpoint:
    1. Counts existing transcripts in the database
    2. Adjusts limit: adjusted_limit = transcript_count + requested_limit
    3. Fetches video IDs from YouTube channel using YouTube Data API v3
    4. Compares and adds only new videos to the video_queue

    Requires YOUTUBE_API_KEY environment variable to be set.
    Get a free API key at: https://console.cloud.google.com/apis/credentials

    Args:
        channel_url: URL of the YouTube channel (@handle, /channel/ID, or /c/custom)
        limit: Number of NEW videos you want in the queue (default: 0 = all videos)
               The actual scrape limit will be automatically increased based on existing transcript count

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

        # Get the current count of transcripts in the database
        cursor = database.cursor
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        transcript_count = cursor.fetchone()[0]

        # Get the current count of videos in the queue
        cursor.execute("SELECT COUNT(*) FROM video_queue")
        queue_size = cursor.fetchone()[0]

        # Add transcript count AND queue size to the requested limit
        # This ensures we scrape far enough past all already-processed and already-queued videos
        adjusted_limit = transcript_count + queue_size + limit

        logger.info(
            f"Transcripts in database: {transcript_count}, "
            f"Videos in queue: {queue_size}, "
            f"Requested limit: {limit}, "
            f"Adjusted limit: {adjusted_limit}"
        )

        # Use async context manager
        async with VideoQueueManager(database) as queue_manager:
            # Execute queue building with adjusted limit
            logger.info(
                f"Building queue from {channel_url} with adjusted limit {adjusted_limit}"
            )
            results = await queue_manager.queue_new_videos(
                channel_url,
                adjusted_limit,
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


@app.post("/queue/cleanup")
def cleanup_video_queue() -> Dict[str, Any]:
    """
    Clean up the video queue by removing videos that already have transcripts.

    This endpoint:
    1. Finds all youtube_ids that exist in both video_queue and transcripts tables
    2. Removes those youtube_ids from video_queue
    3. Returns the count and list of removed IDs

    This is useful for cleaning up duplicates that weren't automatically removed
    during bulk transcript fetching.

    Returns:
        Dict containing cleanup results:
            - success: Whether cleanup succeeded
            - message: Description of what happened
            - removed_count: Number of videos removed from queue
            - removed_ids: List of youtube_ids that were removed

    Raises:
        HTTPException: If database not available or cleanup fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        logger.info("Starting video queue cleanup")
        results = transcript_manager.cleanup_queue()

        if not results.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results.get("error", "Unknown error during cleanup"),
            )

        logger.info(f"Queue cleanup complete: {results['message']}")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup video queue: {str(e)}",
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
    article_id: str, request: CreateArticleRequest
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


@app.patch("/article/{article_id}/bullet-points")
def generate_article_bullet_points(article_id: int):
    """Generate and save bullet points for an existing article."""
    article = database.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found",
        )

    journalist = AureliusStone()
    result = journalist.generate_bullet_points(article["content"])

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    success = database.update_article_bullet_points(article_id, result["bullet_points"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update article",
        )

    return {"article_id": article_id, "bullet_points": result["bullet_points"]}


@app.post("/bullet-points/generate/batch/{amount_of_articles}")
def generate_all_bullet_points(amount_of_articles: int):
    """Generate bullet points for all articles that don't have them."""
    articles = database.get_all_articles()
    journalist = AureliusStone()

    results = {"processed": 0, "skipped": 0, "errors": []}

    for article in articles:
        # Stop if we've processed enough
        if results["processed"] >= amount_of_articles:
            break

        # Skip if already has bullet points
        if article.get("bullet_points"):
            results["skipped"] += 1
            continue

        result = journalist.generate_bullet_points(article["content"])

        if result.get("error"):
            results["errors"].append({"id": article["id"], "error": result["error"]})
            continue

        database.update_article_bullet_points(article["id"], result["bullet_points"])
        results["processed"] += 1

    return results


@app.get("/art/{art_id}/image")
def get_art_image(art_id: int):
    """Serve the image for an art record."""
    art = database.get_art_by_id(art_id)
    if not art or not art.get("image_data"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image for art ID {art_id} not found",
        )

    return Response(content=art["image_data"], media_type="image/png")
