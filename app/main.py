# Standard library imports
import base64
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
import requests

# Local imports
from app import TranscriptManager, ArticleGenerator
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_journalists.fr_j1 import FRJ1
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
from app.content_department.ai_artists.fra1 import FRA1

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
    frj1 = FRJ1()

    # Create/update Aurelius Stone with bio and description
    journalist_manager.upsert_journalist(
        full_name=aurelius.FULL_NAME,
        first_name=aurelius.FIRST_NAME,
        last_name=aurelius.LAST_NAME,
        bio=aurelius.get_bio(),
        description=aurelius.get_description(),
    )

    # Create/update FRJ1 with bio and description
    journalist_manager.upsert_journalist(
        full_name=frj1.FULL_NAME,
        first_name=frj1.FIRST_NAME,
        last_name=frj1.LAST_NAME,
        bio=frj1.get_bio(),
        description=frj1.get_description(),
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


# ===== HELPER FUNCTIONS =====


def _decode_image_url(image_url: str) -> bytes:
    """
    Decode image data from either a base64 data URL or a regular URL.

    Args:
        image_url: Either a base64 data URL (data:image/...) or HTTP URL

    Returns:
        bytes: The raw image data

    Raises:
        HTTPException: If URL download fails
    """
    import base64
    import requests

    if image_url.startswith("data:image"):
        # Handle base64 data URLs (from OpenAI image generation)
        # Format: data:image/png;base64,<base64_data>
        header, base64_data = image_url.split(",", 1)
        return base64.b64decode(base64_data)
    else:
        # Handle regular URLs (from other providers)
        response = requests.get(image_url)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download image: {response.status_code}",
            )
        return response.content


# ===== Pipeline helpers (shared by endpoints and POST /pipeline/run) =====


async def _run_build_queue(
    db: Database, channel_url: str, limit: int
) -> Dict[str, Any]:
    """Build video queue; returns result dict (no HTTPException)."""
    async with VideoQueueManager(db) as queue_manager:
        results = await queue_manager.queue_new_videos(
            channel_url,
            target_new_videos=limit,
        )
    return {
        "success": True,
        "message": f"Queue built successfully from {channel_url}",
        "results": results,
    }


async def _run_bulk_fetch_transcripts(
    db: Database,
    transcript_mgr: TranscriptManager,
    amount: int,
    auto_build: bool,
    channel_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Bulk fetch transcripts from queue; returns result dict (no HTTPException)."""
    import json

    channel_url = channel_url or os.getenv("DEFAULT_YOUTUBE_CHANNEL_URL")
    cursor = db.cursor
    cursor.execute(
        """SELECT COUNT(*)
           FROM video_queue AS T1
           LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
           WHERE T1.transcript_available = 1 AND T2.youtube_id IS NULL"""
    )
    available_count = cursor.fetchone()[0]
    auto_build_triggered = False
    auto_build_added = 0

    if available_count < amount and auto_build and channel_url:
        auto_build_triggered = True
        shortfall = amount - available_count
        try:
            async with VideoQueueManager(db) as queue_manager:
                build_results = await queue_manager.queue_new_videos(
                    channel_url,
                    target_new_videos=shortfall,
                )
            auto_build_added = build_results.get("newly_queued", 0)
        except Exception as e:
            logger.warning(f"Auto-build queue failed: {e}. Proceeding with available.")

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

    results = []
    transcripts_fetched = 0
    transcripts_failed = 0
    RATE_LIMIT_MS = 5000

    for row in queue_items:
        youtube_id = row[0]
        try:
            transcript_result = transcript_mgr.get_transcript(youtube_id)
            if isinstance(transcript_result, JSONResponse):
                error_content = json.loads(transcript_result.body.decode())
                raise Exception(
                    error_content.get("error", "Unknown error during transcript fetch")
                )
            transcripts_fetched += 1
            results.append(
                {
                    "youtube_id": youtube_id,
                    "status": "success",
                    "source": transcript_result.get("source"),
                }
            )
            cursor.execute(
                "DELETE FROM video_queue WHERE youtube_id = ?", (youtube_id,)
            )
            db.conn.commit()
        except Exception as e:
            transcripts_failed += 1
            results.append(
                {"youtube_id": youtube_id, "status": "failed", "error": str(e)}
            )
        time.sleep(RATE_LIMIT_MS / 1000.0)

    message = (
        f"Processed {len(queue_items)} videos from queue"
        if len(queue_items) >= amount
        else f"Processed {len(queue_items)} videos from queue (requested {amount}, only {len(queue_items)} available)"
    )
    response = {
        "success": True,
        "message": message,
        "transcripts_fetched": transcripts_fetched,
        "transcripts_failed": transcripts_failed,
        "results": results,
    }
    if auto_build_triggered:
        response["auto_build"] = {
            "triggered": True,
            "videos_added": auto_build_added,
            "channel_url": channel_url,
        }
    return response


async def _run_bulk_write_articles(
    db: Database,
    journalist_mgr: JournalistManager,
    amount: int,
    journalist: Journalist,
    tone: Tone,
    article_type: ArticleType,
) -> Dict[str, Any]:
    """Bulk write articles from transcripts; returns result dict (no HTTPException)."""
    journalist_classes = {
        Journalist.AURELIUS_STONE: AureliusStone,
        Journalist.FR_J1: FRJ1,
    }
    journalist_class = journalist_classes.get(journalist)
    if not journalist_class:
        raise ValueError(f"Journalist '{journalist.value}' not implemented")
    journalist_instance = journalist_class()
    journalist_data = journalist_mgr.get_journalist(journalist_instance.FULL_NAME)
    if not journalist_data:
        journalist_mgr.upsert_journalist(
            full_name=journalist_instance.FULL_NAME,
            first_name=journalist_instance.FIRST_NAME,
            last_name=journalist_instance.LAST_NAME,
            bio=journalist_instance.get_bio(),
            description=journalist_instance.get_description(),
        )
        journalist_data = journalist_mgr.get_journalist(journalist_instance.FULL_NAME)
    if not journalist_data:
        raise ValueError(
            f"Failed to create or retrieve journalist {journalist_instance.FULL_NAME}"
        )
    journalist_id = journalist_data["id"]

    cursor = db.cursor
    cursor.execute(
        """SELECT t.id, t.committee, t.youtube_id, t.content
           FROM transcripts t
           LEFT JOIN articles a ON t.id = a.transcript_id
           WHERE a.id IS NULL
           ORDER BY t.id ASC
           LIMIT ?""",
        (amount,),
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

    results = []
    articles_generated = 0
    articles_failed = 0
    for row in transcripts:
        transcript_id, committee, youtube_id, transcript_content = (
            row[0],
            row[1],
            row[2],
            row[3],
        )
        try:
            base_context = journalist_instance.load_context(
                tone=tone, article_type=article_type
            )
            full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
            article_result = journalist_instance.generate_article(full_context, "")
            db.add_article(
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
        except Exception as e:
            articles_failed += 1
            results.append(
                {"youtube_id": youtube_id, "status": "failed", "error": str(e)}
            )

    return {
        "success": True,
        "message": f"Processed {len(transcripts)} transcripts",
        "articles_generated": articles_generated,
        "articles_failed": articles_failed,
        "results": results,
    }


def _run_bullet_points_batch(db: Database, amount: int) -> Dict[str, Any]:
    """Generate bullet points for articles that don't have them; returns result dict."""
    articles = db.get_all_articles()
    journalist = AureliusStone()
    results = {"processed": 0, "skipped": 0, "errors": []}
    for article in articles:
        if results["processed"] >= amount:
            break
        if article.get("bullet_points"):
            results["skipped"] += 1
            continue
        result = journalist.generate_bullet_points(article["content"])
        if result.get("error"):
            results["errors"].append({"id": article["id"], "error": result["error"]})
            continue
        db.update_article_bullet_points(article["id"], result["bullet_points"])
        results["processed"] += 1
    return results


def _run_image_batch(
    db: Database, amount: int, artist: Artist, model: ImageModel
) -> Dict[str, Any]:
    """Generate images for articles with bullet_points but no art; returns result dict."""
    artist_classes = {
        Artist.SPECTRA_VERITAS: SpectraVeritas,
        Artist.FRA1: FRA1,
    }
    artist_class = artist_classes.get(artist)
    if not artist_class:
        raise ValueError(f"Artist '{artist.value}' not implemented")
    artist_instance = artist_class()
    cursor = db.cursor
    cursor.execute(
        """SELECT a.id, a.title, a.bullet_points, a.transcript_id
           FROM articles a
           LEFT JOIN art ON a.id = art.article_id
           WHERE a.bullet_points IS NOT NULL AND a.bullet_points != '' AND art.id IS NULL
           LIMIT ?""",
        (amount,),
    )
    articles = cursor.fetchall()
    if not articles:
        return {
            "success": True,
            "message": "No articles found that need images",
            "images_generated": 0,
            "images_failed": 0,
            "results": [],
        }
    results = []
    images_generated = 0
    images_failed = 0
    for row in articles:
        article_id, title, bullet_points, transcript_id = row[0], row[1], row[2], row[3]
        try:
            cursor.execute("SELECT id FROM art WHERE article_id = ?", (article_id,))
            if cursor.fetchone():
                results.append(
                    {
                        "article_id": article_id,
                        "status": "skipped",
                        "reason": "Art exists",
                    }
                )
                continue
            image_result = artist_instance.generate_image(
                title=title, bullet_points=bullet_points, model=model.value
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
                continue
            if image_result.get("image_url"):
                image_data = _decode_image_url(image_result["image_url"])
                art_id = db.add_art(
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
                images_generated += 1
                results.append(
                    {
                        "article_id": article_id,
                        "status": "success",
                        "art_id": art_id,
                        "title": title,
                    }
                )
            else:
                images_failed += 1
                results.append(
                    {
                        "article_id": article_id,
                        "status": "failed",
                        "error": "No image URL",
                    }
                )
        except Exception as e:
            images_failed += 1
            results.append(
                {"article_id": article_id, "status": "failed", "error": str(e)}
            )
    return {
        "success": True,
        "message": f"Processed {len(articles)} articles",
        "images_generated": images_generated,
        "images_failed": images_failed,
        "results": results,
    }


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


@app.delete("/image/delete/{art_id}")
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


@app.delete("/art/delete-all")
def delete_all_art_endpoint() -> Dict[str, Any]:
    """
    Delete ALL art records from the database.

    WARNING: This is destructive and cannot be undone.

    Returns:
        Dict containing count of deleted records
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        deleted_count = database.delete_all_art()

        logger.info(f"Deleted all art: {deleted_count} records")
        return {
            "success": True,
            "message": f"Successfully deleted all art records",
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error(f"Failed to delete all art: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete all art: {str(e)}",
        )


@app.delete("/article/{article_id}")
def delete_article_endpoint(article_id: int) -> Dict[str, Any]:
    """
    Delete an article and its corresponding image.

    This endpoint deletes the article and any art records linked to it.

    Args:
        article_id: The ID of the article to delete

    Returns:
        Dict containing success status and deletion details

    Raises:
        HTTPException: If article not found or database operation fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # First check if article exists
        article = database.get_article_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )

        # Delete any linked art records first
        art_deleted_count = database.delete_art_by_article_id(article_id)

        # Delete the article
        success = database.delete_article_by_id(article_id)

        if success:
            logger.info(
                f"Successfully deleted article {article_id} and {art_deleted_count} linked image(s)"
            )
            return {
                "success": True,
                "message": f"Article {article_id} and linked images deleted successfully",
                "article_id": article_id,
                "images_deleted": art_deleted_count,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete article {article_id}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete article: {str(e)}",
        )


@app.delete("/articles/remove-duplicate-per-transcript")
def remove_duplicate_articles_per_transcript() -> Dict[str, Any]:
    """
    Find transcripts that have more than one article and delete the extra article(s).

    For each transcript_id that has multiple articles, keeps the article with the
    smallest id (first created) and deletes the others, along with their linked art.

    Returns:
        Dict containing:
            - success: Overall status
            - transcripts_affected: Number of transcripts that had duplicates
            - articles_deleted: Number of articles removed
            - art_deleted: Number of art records removed
            - deleted_article_ids: List of article IDs that were deleted
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        cursor = database.cursor
        # Transcripts with more than one article: get article ids to delete (keep MIN(id) per transcript)
        cursor.execute(
            """
            SELECT a.id, a.transcript_id
            FROM articles a
            JOIN (
                SELECT transcript_id, MIN(id) AS keep_id
                FROM articles
                WHERE transcript_id IS NOT NULL
                GROUP BY transcript_id
                HAVING COUNT(*) > 1
            ) sub ON a.transcript_id = sub.transcript_id AND a.id != sub.keep_id
            ORDER BY a.id
            """
        )
        rows = cursor.fetchall()
        to_delete = [r[0] for r in rows]
        transcripts_affected = len(set(r[1] for r in rows))

        if not to_delete:
            return {
                "success": True,
                "message": "No duplicate articles found (each transcript has at most one article).",
                "transcripts_affected": 0,
                "articles_deleted": 0,
                "art_deleted": 0,
                "deleted_article_ids": [],
            }

        articles_deleted = 0
        art_deleted = 0
        for article_id in to_delete:
            art_deleted += database.delete_art_by_article_id(article_id)
            if database.delete_article_by_id(article_id):
                articles_deleted += 1

        logger.info(
            f"Removed duplicate articles: {articles_deleted} articles, {art_deleted} art records; ids={to_delete}"
        )
        return {
            "success": True,
            "message": f"Deleted {articles_deleted} duplicate article(s) from {transcripts_affected} transcript(s), and {art_deleted} linked art record(s).",
            "transcripts_affected": transcripts_affected,
            "articles_deleted": articles_deleted,
            "art_deleted": art_deleted,
            "deleted_article_ids": to_delete,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove duplicate articles failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remove duplicate articles failed: {str(e)}",
        )


@app.get("/transcripts/without-articles")
def get_transcripts_without_articles() -> Dict[str, Any]:
    """
    List transcripts that have no article.

    Returns transcripts in the database for which there is no article with
    matching transcript_id. Useful to see which meetings still need an article.

    Returns:
        Dict containing:
            - success: Status
            - count: Number of transcripts with no article
            - transcripts: List of { id, youtube_id, committee, meeting_date, video_title }
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        cursor = database.cursor
        cursor.execute(
            """
            SELECT t.id, t.youtube_id, t.committee, t.meeting_date, t.video_title
            FROM transcripts t
            WHERE NOT EXISTS (
                SELECT 1 FROM articles a WHERE a.transcript_id = t.id
            )
            ORDER BY t.id
            """
        )
        rows = cursor.fetchall()
        transcripts = [
            {
                "id": r[0],
                "youtube_id": r[1],
                "committee": r[2],
                "meeting_date": r[3],
                "video_title": r[4],
            }
            for r in rows
        ]
        return {
            "success": True,
            "count": len(transcripts),
            "transcripts": transcripts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Get transcripts without articles failed: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get transcripts without articles failed: {str(e)}",
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
       - Fetch transcript using TranscriptManager (tries YouTube Data API v3 captions endpoints first, falls back to Whisper)
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
    - POST `/queue/build` - Populate video_queue by discovering YouTube channel videos
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
        return await _run_bulk_fetch_transcripts(
            database, transcript_manager, amount, auto_build
        )
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


@app.post("/articles/strip-h1-tags")
async def strip_h1_tags_from_articles() -> Dict[str, Any]:
    """
    Strip all H1 tags (and their content) from all articles.

    H1 tags are duplicate titles since articles already have a title field.
    This endpoint removes them from existing articles.

    Returns:
        Dict containing count of articles modified
    """
    import re

    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not initialized",
            )

        # Get all articles from database
        all_articles = database.get_all_articles()

        # Pattern to match H1 tags and their content (including multiline)
        h1_pattern = re.compile(r"<h1[^>]*>.*?</h1>", re.DOTALL | re.IGNORECASE)

        modified_count = 0
        modified_ids = []

        for article in all_articles:
            content = article.get("content", "")
            if content and h1_pattern.search(content):
                # Remove H1 tags and their content
                new_content = h1_pattern.sub("", content)
                # Clean up any resulting double newlines
                new_content = re.sub(r"\n\s*\n\s*\n", "\n\n", new_content)

                # Update in database
                if database.update_article_content(article["id"], new_content):
                    modified_count += 1
                    modified_ids.append(article["id"])

                    # Also update in-memory cache if it exists
                    if article["id"] in articles_db:
                        articles_db[article["id"]]["content"] = new_content

        logger.info(f"Stripped H1 tags from {modified_count} articles")
        return {
            "message": f"Successfully processed articles",
            "articles_modified": modified_count,
            "modified_article_ids": modified_ids,
            "total_articles_scanned": len(all_articles),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to strip H1 tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to strip H1 tags: {str(e)}",
        )


@app.post("/articles/strip-fall-river-from-titles")
async def strip_fall_river_from_titles() -> Dict[str, Any]:
    """
    Remove 'Fall River' from all article titles.

    Since the publication is about Fall River, having it in every title is redundant.
    This endpoint removes variations like 'Fall River', 'Fall River's', etc.

    Returns:
        Dict containing count of articles modified
    """
    import re

    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not initialized",
            )

        # Get all articles from database
        all_articles = database.get_all_articles()

        # Pattern to match "Fall River" and variations (case insensitive)
        # Handles: "Fall River", "Fall River's", "Fall River:", etc.
        fall_river_pattern = re.compile(r"\bFall River'?s?\b[:\s]*", re.IGNORECASE)

        modified_count = 0
        modified_articles = []

        for article in all_articles:
            title = article.get("title", "")
            if title and fall_river_pattern.search(title):
                # Remove "Fall River" and clean up
                new_title = fall_river_pattern.sub("", title)
                # Clean up any resulting double spaces or leading/trailing spaces
                new_title = re.sub(r"\s+", " ", new_title).strip()
                # Capitalize first letter if it's now lowercase
                if new_title and new_title[0].islower():
                    new_title = new_title[0].upper() + new_title[1:]

                # Update in database
                if new_title and database.update_article_title(
                    article["id"], new_title
                ):
                    modified_count += 1
                    modified_articles.append(
                        {
                            "id": article["id"],
                            "old_title": title,
                            "new_title": new_title,
                        }
                    )

                    # Also update in-memory cache if it exists
                    if article["id"] in articles_db:
                        articles_db[article["id"]]["title"] = new_title

        logger.info(f"Removed 'Fall River' from {modified_count} article titles")
        return {
            "message": f"Successfully processed articles",
            "articles_modified": modified_count,
            "modified_articles": modified_articles,
            "total_articles_scanned": len(all_articles),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to strip Fall River from titles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to strip Fall River from titles: {str(e)}",
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
            Journalist.FR_J1: FRJ1,
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
    model: ImageModel = ImageModel.GPT_IMAGE_1,
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
        model: Image model to use (default: gpt-image-1)

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
        return _run_image_batch(database, amount, artist_name, model)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
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
    model: ImageModel = ImageModel.GPT_IMAGE_1,
):
    """
    Generate an image using the xAI Aurora API.
    """
    # Map artist enum values to their classes
    artist_classes = {
        Artist.SPECTRA_VERITAS: SpectraVeritas,
        Artist.FRA1: FRA1,
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

    # Check if article already has art
    cursor = database.cursor
    cursor.execute("SELECT id FROM art WHERE article_id = ?", (article_id,))
    existing_art = cursor.fetchone()
    if existing_art:
        return {
            "image_url": None,
            "error": f"Article {article_id} already has art (art_id: {existing_art[0]}). Use DELETE /art/delete/{existing_art[0]} first to regenerate.",
            "article_id": article_id,
            "existing_art_id": existing_art[0],
        }

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
        try:
            image_data = _decode_image_url(image_result["image_url"])
            art_id = database.add_art(
                prompt=image_result["prompt_used"],
                image_url=None,
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
        except HTTPException as e:
            image_result["error"] = e.detail

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
        journalist_data = journalist_manager.get_journalist(
            journalist_instance.FULL_NAME
        )
        if not journalist_data:
            # Create the journalist if it doesn't exist
            journalist_manager.upsert_journalist(
                full_name=journalist_instance.FULL_NAME,
                first_name=journalist_instance.FIRST_NAME,
                last_name=journalist_instance.LAST_NAME,
                bio=journalist_instance.get_bio(),
                description=journalist_instance.get_description(),
            )
            # Get the journalist data again after creation
            journalist_data = journalist_manager.get_journalist(
                journalist_instance.FULL_NAME
            )
            if not journalist_data:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create or retrieve journalist '{journalist_instance.FULL_NAME}'",
                )
        journalist_id = journalist_data["id"]
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
    transcript_id: int,
    additional_context: str = "",
    journalist: Journalist = Journalist.AURELIUS_STONE,  # This creates the dropdown
    tone: Optional[Tone] = None,
    article_type: Optional[ArticleType] = None,
) -> Dict[str, Any]:
    """
    Generate an article from a transcript without writing to the database.

    This endpoint:
    - Fetches a transcript from the database using the provided transcript_id
    - Generates an article using the specified journalist, tone, and article type
    - Returns the article content and metadata

    Note: This endpoint does NOT write to the database. It only returns the generated
    article and its metadata for preview/testing purposes.

    Args:
        transcript_id: ID of the transcript to generate an article from
        additional_context: Optional additional context to provide to the journalist
        journalist: Journalist to write the article (default: Aurelius Stone)
        tone: Writing tone for the article (optional, uses journalist default if not provided)
        article_type: Type of article to generate (optional, uses journalist default if not provided)

    Returns:
        Dict containing:
            - journalist: Name of the journalist who generated the article
            - context: Full context used for article generation
            - article_title: Generated article title
            - article_content: Generated article content
            - transcript_id: ID of the transcript used
            - transcript_content_length: Length of the transcript content

    Raises:
        HTTPException: If database not available, transcript not found, or generation fails
    """
    try:
        # Fetch transcript content from database
        if not database:
            raise HTTPException(status_code=500, detail="Database not available")

        transcript_data = database.get_transcript_by_id(transcript_id)
        if not transcript_data:
            raise HTTPException(
                status_code=404, detail=f"No transcript found with ID {transcript_id}"
            )

        # Extract content from transcript data (content is at index 3)
        transcript_content = transcript_data[3]

        # Map journalist enum to class instances
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
            Journalist.FR_J1: FRJ1,
        }

        # Get journalist instance
        journalist_class = journalist_classes.get(journalist)
        if not journalist_class:
            available_journalists = [j.value for j in Journalist]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journalist '{journalist.value}' not implemented yet. Available journalists: {available_journalists}",
            )

        journalist_instance = journalist_class()
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
            f"Article generated successfully by {journalist_instance.NAME} using transcript ID {transcript_id}"
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
            "transcript_id": transcript_id,
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
    journalist: Journalist = Journalist.FR_J1,
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
        return await _run_bulk_write_articles(
            database,
            journalist_manager,
            amount_of_articles,
            journalist,
            tone,
            article_type,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk article generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk article generation failed: {str(e)}",
        )


@app.post("/sync-article-to-wordpress/{article_id}")
def sync_article_to_wordpress(article_id: int) -> Dict[str, Any]:
    """
    Fetch an article from the FastAPI database and POST it to the WordPress create-article endpoint.

    Args:
        article_id: The ID of the article to sync

    Returns:
        Dict containing the WordPress API response
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Fetch article from database
        article = database.get_article_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )

        # Get journalist first_name and last_name and combine into journalist_name
        journalist_name = ""
        if article.get("journalist_id"):
            try:
                database.cursor.execute(
                    "SELECT first_name, last_name FROM journalists WHERE id = ?",
                    (article["journalist_id"],),
                )
                journalist_result = database.cursor.fetchone()
                if journalist_result:
                    first_name = journalist_result[0] or ""
                    last_name = journalist_result[1] or ""
                    if first_name and last_name:
                        journalist_name = f"{first_name} {last_name}"
                    elif first_name:
                        journalist_name = first_name
                    elif last_name:
                        journalist_name = last_name
            except Exception as e:
                logger.warning(f"Failed to fetch journalist data: {str(e)}")

        # Get meeting date from transcript (not article creation date)
        meeting_date = ""
        transcript_id = article.get("transcript_id")
        if transcript_id:
            try:
                database.cursor.execute(
                    "SELECT meeting_date FROM transcripts WHERE id = ?",
                    (transcript_id,),
                )
                transcript_result = database.cursor.fetchone()
                if transcript_result and transcript_result[0]:
                    date_str = transcript_result[0]
                    try:
                        # Try multiple date formats that might be in the database
                        date_obj = None

                        # Try mm-dd-yyyy format (e.g., "11-26-2025")
                        try:
                            date_obj = datetime.strptime(date_str, "%m-%d-%Y")
                        except ValueError:
                            pass

                        # Try mm/dd/yyyy format
                        if not date_obj:
                            try:
                                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                            except ValueError:
                                pass

                        # Try ISO format (YYYY-MM-DD or with time)
                        if not date_obj:
                            try:
                                if date_str.endswith("Z"):
                                    date_str = date_str.replace("Z", "+00:00")
                                date_obj = datetime.fromisoformat(date_str)
                            except ValueError:
                                pass

                        # Try YYYY-MM-DD format
                        if not date_obj:
                            try:
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            except ValueError:
                                pass

                        if date_obj:
                            # Format as ISO date (YYYY-MM-DD) for WordPress
                            meeting_date = date_obj.strftime("%Y-%m-%d")
                        else:
                            # If all parsing attempts failed, use original value
                            logger.warning(
                                f"Could not parse meeting_date '{date_str}', using as-is"
                            )
                            meeting_date = date_str
                    except Exception as e:
                        logger.warning(
                            f"Failed to format meeting_date: {str(e)}, using original value"
                        )
                        meeting_date = transcript_result[0]
            except Exception as e:
                logger.warning(
                    f"Failed to fetch meeting_date from transcript: {str(e)}"
                )

        # Get image data from art record if available
        featured_image = None
        try:
            # Query for art record linked to this article
            database.cursor.execute(
                "SELECT id, image_data, model FROM art WHERE article_id = ? LIMIT 1",
                (article_id,),
            )
            art_result = database.cursor.fetchone()

            if art_result:
                logger.info(
                    f"Found art record for article {article_id}: art_id={art_result[0]}, "
                    f"has_image_data={art_result[1] is not None}, "
                    f"image_data_type={type(art_result[1])}"
                )

                if art_result[1]:  # art_result[1] is image_data
                    image_data = art_result[1]  # bytes

                    # Check if image_data is actually bytes
                    if not isinstance(image_data, bytes):
                        logger.warning(
                            f"Image data for article {article_id} is not bytes, "
                            f"got {type(image_data)} instead"
                        )
                    else:
                        # Auto-detect image format from magic bytes
                        image_format = "png"  # default
                        if len(image_data) >= 2:
                            # JPEG starts with 0xFF 0xD8
                            if image_data[:2] == b"\xff\xd8":
                                image_format = "jpeg"
                            # PNG starts with 0x89 0x50 0x4E 0x47
                            elif (
                                len(image_data) >= 8
                                and image_data[:8] == b"\x89PNG\r\n\x1a\n"
                            ):
                                image_format = "png"

                        # Encode image_data bytes to base64
                        base64_data = base64.b64encode(image_data).decode("utf-8")

                        # Format as WordPress data URL
                        featured_image = (
                            f"data:image/{image_format};base64,{base64_data}"
                        )

                        logger.info(
                            f"Successfully processed image for article {article_id} "
                            f"(art_id: {art_result[0]}, format: {image_format}, "
                            f"size: {len(image_data)} bytes, base64_length: {len(base64_data)})"
                        )
                else:
                    logger.info(
                        f"Art record found for article {article_id} but image_data is None/empty"
                    )
            else:
                logger.info(f"No art record found for article {article_id}")
        except Exception as e:
            # Log warning but don't fail the sync if image can't be processed
            logger.warning(
                f"Failed to fetch/process image for article {article_id}: {str(e)}",
                exc_info=True,
            )

        # Validate that article has content, bullet points, and art before syncing
        missing_fields = []
        if not article.get("content"):
            missing_fields.append("content")
        if not article.get("bullet_points"):
            missing_fields.append("bullet_points")
        if not featured_image:
            missing_fields.append("featured_image (art)")

        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Article {article_id} is missing required fields for sync: {', '.join(missing_fields)}. Article must have content, bullet points, and art to sync to WordPress.",
            )

        # Build WordPress payload
        payload = {
            "title": article.get("title") or "",
            "article_content": article.get("content") or "",
            "journalist_name": journalist_name or "",
            "committee": article.get("committee") or "",
            "youtube_id": article.get("youtube_id") or "",
            "bullet_points": article.get("bullet_points") or "",
            "meeting_date": meeting_date or "",
            "view_count": article.get("view_count") or 0,
            "featured_image": featured_image or "",
            "status": "publish",
        }

        if featured_image:
            logger.info(
                f"Added featured_image to payload for article {article_id} "
                f"(length: {len(featured_image)} chars)"
            )
        else:
            logger.info(f"No featured_image to add for article {article_id}")

        # Log the payload being sent (excluding large content and image fields)
        payload_log = payload.copy()
        if payload_log.get("article_content"):
            payload_log["article_content"] = (
                f"[{len(payload_log['article_content'])} chars]"
            )
        if payload_log.get("featured_image"):
            # Log image size without the actual base64 data
            image_size = len(featured_image) if featured_image else 0
            payload_log["featured_image"] = f"[{image_size} chars base64]"
        logger.info(
            f"Sending payload to WordPress for article {article_id}: {payload_log}"
        )

        # POST to WordPress endpoint
        wordpress_url = "http://192.168.1.17:9004/wp-json/fr-mirror/v2/create-article"
        try:
            response = requests.post(
                wordpress_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()

            logger.info(f"Successfully synced article {article_id} to WordPress")
            return {
                "success": True,
                "article_id": article_id,
                "wordpress_response": response.json(),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to POST to WordPress: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to sync to WordPress: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to sync article {article_id} to WordPress: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync article: {str(e)}",
        )


@app.post("/sync-articles-to-wordpress")
def sync_all_articles_to_wordpress(limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Sync multiple articles to WordPress in bulk.

    This endpoint:
    1. Fetches all articles from the database (with optional limit)
    2. Iterates through each article and syncs it to WordPress
    3. Continues processing even if individual articles fail
    4. Returns a summary with counts of successful and failed syncs

    Args:
        limit: Optional maximum number of articles to sync. If not provided, syncs all articles.

    Returns:
        Dict containing:
            - success: Overall operation status
            - total_articles: Total articles processed
            - synced: Count of successfully synced articles
            - failed: Count of failed syncs
            - errors: List of error details (article_id and error message)
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Fetch all articles from database
        all_articles = database.get_all_articles()

        # Apply limit if provided
        if limit is not None and limit > 0:
            articles_to_sync = all_articles[:limit]
        else:
            articles_to_sync = all_articles

        if not articles_to_sync:
            return {
                "success": True,
                "total_articles": 0,
                "synced": 0,
                "failed": 0,
                "errors": [],
                "message": "No articles found to sync",
            }

        logger.info(
            f"Starting bulk sync to WordPress: {len(articles_to_sync)} articles"
        )

        synced_count = 0
        failed_count = 0
        errors = []
        wordpress_url = "http://192.168.1.17:9004/wp-json/fr-mirror/v2/create-article"

        # Loop through each article and sync
        for article in articles_to_sync:
            article_id = article.get("id")
            if not article_id:
                failed_count += 1
                errors.append(
                    {
                        "article_id": None,
                        "error": "Article missing ID field",
                    }
                )
                continue

            try:
                # Get journalist first_name and last_name and combine into journalist_name
                journalist_name = ""
                if article.get("journalist_id"):
                    try:
                        database.cursor.execute(
                            "SELECT first_name, last_name FROM journalists WHERE id = ?",
                            (article["journalist_id"],),
                        )
                        journalist_result = database.cursor.fetchone()
                        if journalist_result:
                            first_name = journalist_result[0] or ""
                            last_name = journalist_result[1] or ""
                            if first_name and last_name:
                                journalist_name = f"{first_name} {last_name}"
                            elif first_name:
                                journalist_name = first_name
                            elif last_name:
                                journalist_name = last_name
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch journalist data for article {article_id}: {str(e)}"
                        )

                # Get meeting date from transcript (not article creation date)
                meeting_date = ""
                transcript_id = article.get("transcript_id")
                if transcript_id:
                    try:
                        database.cursor.execute(
                            "SELECT meeting_date FROM transcripts WHERE id = ?",
                            (transcript_id,),
                        )
                        transcript_result = database.cursor.fetchone()
                        if transcript_result and transcript_result[0]:
                            date_str = transcript_result[0]
                            try:
                                # Try multiple date formats that might be in the database
                                date_obj = None

                                # Try mm-dd-yyyy format (e.g., "11-26-2025")
                                try:
                                    date_obj = datetime.strptime(date_str, "%m-%d-%Y")
                                except ValueError:
                                    pass

                                # Try mm/dd/yyyy format
                                if not date_obj:
                                    try:
                                        date_obj = datetime.strptime(
                                            date_str, "%m/%d/%Y"
                                        )
                                    except ValueError:
                                        pass

                                # Try ISO format (YYYY-MM-DD or with time)
                                if not date_obj:
                                    try:
                                        if date_str.endswith("Z"):
                                            date_str = date_str.replace("Z", "+00:00")
                                        date_obj = datetime.fromisoformat(date_str)
                                    except ValueError:
                                        pass

                                # Try YYYY-MM-DD format
                                if not date_obj:
                                    try:
                                        date_obj = datetime.strptime(
                                            date_str, "%Y-%m-%d"
                                        )
                                    except ValueError:
                                        pass

                                if date_obj:
                                    # Format as ISO date (YYYY-MM-DD) for WordPress
                                    meeting_date = date_obj.strftime("%Y-%m-%d")
                                else:
                                    # If all parsing attempts failed, use original value
                                    logger.warning(
                                        f"Could not parse meeting_date '{date_str}' for article {article_id}, using as-is"
                                    )
                                    meeting_date = date_str
                            except Exception as e:
                                logger.warning(
                                    f"Failed to format meeting_date for article {article_id}: {str(e)}, using original value"
                                )
                                meeting_date = transcript_result[0]
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch meeting_date from transcript for article {article_id}: {str(e)}"
                        )

                # Get image data from art record if available
                featured_image = None
                try:
                    # Query for art record linked to this article
                    database.cursor.execute(
                        "SELECT id, image_data, model FROM art WHERE article_id = ? LIMIT 1",
                        (article_id,),
                    )
                    art_result = database.cursor.fetchone()

                    if art_result and art_result[1]:  # art_result[1] is image_data
                        image_data = art_result[1]  # bytes

                        # Check if image_data is actually bytes
                        if isinstance(image_data, bytes):
                            # Auto-detect image format from magic bytes
                            image_format = "png"  # default
                            if len(image_data) >= 2:
                                # JPEG starts with 0xFF 0xD8
                                if image_data[:2] == b"\xff\xd8":
                                    image_format = "jpeg"
                                # PNG starts with 0x89 0x50 0x4E 0x47
                                elif (
                                    len(image_data) >= 8
                                    and image_data[:8] == b"\x89PNG\r\n\x1a\n"
                                ):
                                    image_format = "png"

                            # Encode image_data bytes to base64
                            base64_data = base64.b64encode(image_data).decode("utf-8")

                            # Format as WordPress data URL
                            featured_image = (
                                f"data:image/{image_format};base64,{base64_data}"
                            )
                except Exception as e:
                    # Log warning but don't fail the sync if image can't be processed
                    logger.warning(
                        f"Failed to fetch/process image for article {article_id}: {str(e)}"
                    )

                # Validate that article has content, bullet points, and art before syncing
                missing_fields = []
                if not article.get("content"):
                    missing_fields.append("content")
                if not article.get("bullet_points"):
                    missing_fields.append("bullet_points")
                if not featured_image:
                    missing_fields.append("featured_image (art)")

                if missing_fields:
                    failed_count += 1
                    error_msg = f"Missing required fields: {', '.join(missing_fields)}"
                    errors.append(
                        {"article_id": article_id, "error": error_msg, "skipped": True}
                    )
                    logger.info(f"Skipping article {article_id}: {error_msg}")
                    continue

                # Build WordPress payload
                payload = {
                    "title": article.get("title") or "",
                    "article_content": article.get("content") or "",
                    "journalist_name": journalist_name or "",
                    "committee": article.get("committee") or "",
                    "youtube_id": article.get("youtube_id") or "",
                    "bullet_points": article.get("bullet_points") or "",
                    "meeting_date": meeting_date or "",
                    "view_count": article.get("view_count") or 0,
                    "featured_image": featured_image or "",
                    "status": "publish",
                }

                # POST to WordPress endpoint
                response = requests.post(
                    wordpress_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()

                synced_count += 1
                logger.info(f"Successfully synced article {article_id} to WordPress")

            except requests.exceptions.RequestException as e:
                failed_count += 1
                error_msg = f"Failed to POST to WordPress: {str(e)}"
                errors.append({"article_id": article_id, "error": error_msg})
                logger.error(
                    f"Failed to sync article {article_id} to WordPress: {error_msg}"
                )
            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to sync article: {str(e)}"
                errors.append({"article_id": article_id, "error": error_msg})
                logger.error(
                    f"Failed to sync article {article_id} to WordPress: {error_msg}",
                    exc_info=True,
                )

        logger.info(
            f"Bulk sync complete: {synced_count} succeeded, {failed_count} failed out of {len(articles_to_sync)} total"
        )

        return {
            "success": True,
            "total_articles": len(articles_to_sync),
            "synced": synced_count,
            "failed": failed_count,
            "errors": errors,
            "message": f"Synced {synced_count} of {len(articles_to_sync)} articles to WordPress",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk sync to WordPress failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk sync to WordPress failed: {str(e)}",
        )


@app.post("/queue/build")
async def build_video_queue(
    limit: int = 5,
    channel_url: str = os.environ.get("DEFAULT_YOUTUBE_CHANNEL_URL", ""),
) -> Dict[str, Any]:
    """
    Build the video queue by discovering videos from a YouTube channel using YouTube API.

    This endpoint continues scraping videos until the requested number of NEW videos
    are added to the queue, skipping videos that already have transcripts or are
    already in the queue.

    Requires YOUTUBE_API_KEY environment variable to be set.
    Get a free API key at: https://console.cloud.google.com/apis/credentials

    Args:
        channel_url: URL of the YouTube channel (@handle, /channel/ID, or /c/custom)
        limit: Number of NEW videos you want added to the queue (default: 5, 0 = all videos)
               The system will continue scraping until this many new videos are queued

    Returns:
        Dict containing queue building results:
            - total_discovered: Number of videos found on YouTube
            - already_exists: Number of videos that already have transcripts
            - already_in_queue: Number of videos already in the queue
            - newly_queued: Number of videos added to queue (should match limit)
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
        logger.info(
            f"Building queue from {channel_url} - will continue until {limit} new videos are queued"
        )
        return await _run_build_queue(database, channel_url, limit)
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


@app.delete("/queue/clear")
def clear_video_queue() -> Dict[str, Any]:
    """
    Delete all videos from the video queue.

    This endpoint completely clears the video_queue table, removing all queued videos.
    Use this when you want to start fresh with a new queue.

    **WARNING**: This action cannot be undone. All queued videos will be permanently removed.

    Returns:
        Dict containing deletion results:
            - success: Whether deletion succeeded
            - message: Description of what happened
            - deleted_count: Number of videos removed from queue

    Raises:
        HTTPException: If database not available or deletion fails
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        logger.info("Starting video queue clear (deleting all entries)")

        cursor = database.cursor

        # Get count before deletion for reporting
        cursor.execute("SELECT COUNT(*) FROM video_queue")
        count_before = cursor.fetchone()[0]

        # Delete all rows from video_queue
        cursor.execute("DELETE FROM video_queue")
        database.conn.commit()

        logger.info(f"Cleared video queue: removed {count_before} videos")

        return {
            "success": True,
            "message": f"Successfully cleared video queue",
            "deleted_count": count_before,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear video queue: {str(e)}",
        )


@app.post("/pipeline/run")
async def run_data_pipeline(
    amount: int,
    channel_url: Optional[str] = None,
    auto_build: bool = True,
    journalist: Journalist = Journalist.FR_J1,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.NEWS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
) -> Dict[str, Any]:
    """
    Run the full data pipeline using shared logic: build queue, fetch transcripts,
    write articles, generate bullet points, generate images. Artist is always FRA1.
    Each step persists to the database.
    """
    if not database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be a positive integer",
        )
    channel_url = channel_url or os.environ.get("DEFAULT_YOUTUBE_CHANNEL_URL", "")
    artist = Artist.FRA1

    aggregated = {
        "success": True,
        "message": "Pipeline run complete",
        "amount": amount,
        "queue_build": None,
        "transcript_fetch": None,
        "article_write": None,
        "bullet_points": None,
        "image_generate": None,
    }

    try:
        aggregated["queue_build"] = await _run_build_queue(
            database, channel_url, amount
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["queue_build"] = {"error": str(e)}
        logger.error(f"Pipeline queue build failed: {e}")
        return aggregated

    try:
        aggregated["transcript_fetch"] = await _run_bulk_fetch_transcripts(
            database, transcript_manager, amount, auto_build, channel_url
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["transcript_fetch"] = {"error": str(e)}
        logger.error(f"Pipeline transcript fetch failed: {e}")
        return aggregated

    try:
        aggregated["article_write"] = await _run_bulk_write_articles(
            database,
            journalist_manager,
            amount,
            journalist,
            tone,
            article_type,
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["article_write"] = {"error": str(e)}
        logger.error(f"Pipeline article write failed: {e}")
        return aggregated

    try:
        aggregated["bullet_points"] = _run_bullet_points_batch(database, amount)
    except Exception as e:
        aggregated["success"] = False
        aggregated["bullet_points"] = {"error": str(e)}
        logger.error(f"Pipeline bullet points failed: {e}")
        return aggregated

    try:
        aggregated["image_generate"] = _run_image_batch(database, amount, artist, model)
    except Exception as e:
        aggregated["success"] = False
        aggregated["image_generate"] = {"error": str(e)}
        logger.error(f"Pipeline image generate failed: {e}")
        return aggregated

    return aggregated


@app.get("/transcripts/pending/{journalist}")
def get_pending_transcripts(journalist: Journalist) -> Dict[str, Any]:
    """
    Get transcripts that don't have an article from a specific journalist.

    Args:
        journalist: The journalist to check (from enum)

    Returns:
        Dict containing:
            - count: Number of transcripts without articles from this journalist
            - transcripts: List of transcript details (id, youtube_id, committee)
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Map journalist enum to class
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
            Journalist.FR_J1: FRJ1,
        }

        journalist_class = journalist_classes.get(journalist)
        if not journalist_class:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journalist '{journalist.value}' not implemented yet",
            )

        journalist_instance = journalist_class()

        # Ensure journalist exists in database, create if not
        journalist_data = journalist_manager.get_journalist(
            journalist_instance.FULL_NAME
        )
        if not journalist_data:
            # Create the journalist if it doesn't exist
            journalist_manager.upsert_journalist(
                full_name=journalist_instance.FULL_NAME,
                first_name=journalist_instance.FIRST_NAME,
                last_name=journalist_instance.LAST_NAME,
                bio=journalist_instance.get_bio(),
                description=journalist_instance.get_description(),
            )
            # Get the journalist data again after creation
            journalist_data = journalist_manager.get_journalist(
                journalist_instance.FULL_NAME
            )
            if not journalist_data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create or retrieve journalist '{journalist_instance.FULL_NAME}'",
                )

        journalist_id = journalist_data["id"]

        cursor = database.cursor
        cursor.execute(
            """SELECT t.id, t.youtube_id, t.committee
               FROM transcripts t 
               LEFT JOIN articles a ON t.id = a.transcript_id AND a.journalist_id = ?
               WHERE a.id IS NULL
               ORDER BY t.id""",
            (journalist_id,),
        )
        rows = cursor.fetchall()

        meetings = [
            {"transcript_id": row[0], "youtube_id": row[1], "meeting": row[2]}
            for row in rows
        ]

        # Get total transcript count for context
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        total_transcripts = cursor.fetchone()[0]
        covered = total_transcripts - len(meetings)

        return {
            "journalist": journalist.value,
            "summary": f"{journalist.value} has written articles for {covered} of {total_transcripts} meetings. {len(meetings)} meetings have no article from this journalist yet.",
            "articles_written": covered,
            "awaiting_article": len(meetings),
            "total_meetings": total_transcripts,
            "meetings_without_article": meetings,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pending transcripts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending transcripts: {str(e)}",
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


@app.patch("/image/{art_id}/regenerate")
def regenerate_art_image(
    art_id: int,
    artist_name: Artist = Artist.SPECTRA_VERITAS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
) -> Dict[str, Any]:
    """
    Regenerate the image for an existing art record.

    This endpoint regenerates the image using the AI artist, updating the art record
    with a new image while preserving the article association.

    Args:
        art_id: The ID of the art record to regenerate
        artist_name: AI artist to use (default: Spectra Veritas)
        model: Image model to use (default: gpt-image-1)

    Returns:
        Dict containing the updated art metadata

    Raises:
        HTTPException: If art not found, article not found, or article has no bullet points
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        # Step 1: Get existing art record
        art = database.get_art_by_id(art_id)
        if not art:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Art with ID {art_id} not found",
            )

        # Step 2: Get linked article
        article_id = art.get("article_id")
        if not article_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Art {art_id} has no linked article",
            )

        article = database.get_article_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Linked article {article_id} not found",
            )

        # Step 3: Validate article has bullet_points
        bullet_points = article.get("bullet_points")
        if not bullet_points:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Article {article_id} has no bullet points. Generate bullet points first using PATCH /article/{article_id}/bullet-points",
            )

        # Step 4: Create artist instance and generate new image
        artist_classes = {
            Artist.SPECTRA_VERITAS: SpectraVeritas,
            Artist.FRA1: FRA1,
        }
        artist_class = artist_classes.get(artist_name)
        if not artist_class:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Artist '{artist_name.value}' not implemented",
            )

        artist_instance = artist_class()
        logger.info(f"Regenerating image for art ID {art_id} (article: {article_id})")

        image_result = artist_instance.generate_image(
            title=article["title"],
            bullet_points=bullet_points,
            model=model.value,
        )

        if image_result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image generation failed: {image_result['error']}",
            )

        # Step 5: Process the image and update the art record
        if not image_result.get("image_url"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No image URL returned from generation",
            )

        image_data = _decode_image_url(image_result["image_url"])

        # Update the art record
        success = database.update_art_image(
            art_id=art_id,
            prompt=image_result["prompt_used"],
            image_data=image_data,
            medium=image_result.get("medium"),
            aesthetic=image_result.get("aesthetic"),
            model=model.value,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update art record",
            )

        logger.info(f"Successfully regenerated image for art ID {art_id}")

        return {
            "success": True,
            "art_id": art_id,
            "article_id": article_id,
            "title": article["title"],
            "model": model.value,
            "medium": image_result.get("medium"),
            "aesthetic": image_result.get("aesthetic"),
            "prompt_used": image_result["prompt_used"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to regenerate art image {art_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate art image: {str(e)}",
        )


@app.post("/bullet-points/generate/batch/{amount_of_articles}")
def generate_all_bullet_points(amount_of_articles: int):
    """Generate bullet points for all articles that don't have them."""
    if not database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    return _run_bullet_points_batch(database, amount_of_articles)


@app.get("/image/{art_id}")
def get_art_image(art_id: int):
    """Serve the image for an art record."""
    art = database.get_art_by_id(art_id)
    if not art or not art.get("image_data"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image for art ID {art_id} not found",
        )

    return Response(content=art["image_data"], media_type="image/png")


@app.delete("/art/cleanup-duplicates")
def cleanup_duplicate_art() -> Dict[str, Any]:
    """
    Find and delete duplicate art records for articles.
    For each article with multiple art records, keeps the oldest one and deletes the rest.

    Returns:
        Dict containing cleanup results with counts and deleted art IDs
    """
    try:
        if not database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )

        cursor = database.cursor

        # Find all article_ids that have multiple art records
        cursor.execute(
            """SELECT article_id, COUNT(*) as count
               FROM art
               WHERE article_id IS NOT NULL
               GROUP BY article_id
               HAVING COUNT(*) > 1"""
        )
        duplicates = cursor.fetchall()

        if not duplicates:
            return {
                "success": True,
                "message": "No duplicate art records found",
                "articles_with_duplicates": 0,
                "total_deleted": 0,
                "deleted_art_ids": [],
            }

        deleted_art_ids = []
        articles_processed = 0

        for row in duplicates:
            article_id = row[0]
            count = row[1]

            # Get all art records for this article, ordered by created_date (oldest first)
            cursor.execute(
                """SELECT id, created_date
                   FROM art
                   WHERE article_id = ?
                   ORDER BY created_date ASC""",
                (article_id,),
            )
            art_records = cursor.fetchall()

            # Keep the first (oldest) one, delete the rest
            if len(art_records) > 1:
                # Skip the first one, delete all others
                for art_record in art_records[1:]:
                    art_id = art_record[0]
                    success = database.delete_art_by_id(art_id)
                    if success:
                        deleted_art_ids.append(art_id)
                        logger.info(
                            f"Deleted duplicate art ID {art_id} for article {article_id}"
                        )

                articles_processed += 1

        return {
            "success": True,
            "message": f"Cleaned up duplicates for {articles_processed} articles",
            "articles_with_duplicates": articles_processed,
            "total_deleted": len(deleted_art_ids),
            "deleted_art_ids": deleted_art_ids,
        }

    except Exception as e:
        logger.error(f"Failed to cleanup duplicate art: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup duplicate art: {str(e)}",
        )
