# Standard library imports
from datetime import datetime
from enum import Enum
import logging
import sqlite3
from typing import Dict, Any

# Third-party imports
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

# Local imports
from app import TranscriptManager, ArticleGenerator, YouTubeCrawler
from .xai_processor import XAIProcessor 
from .data_classes import ArticleType, Committee, Tone, GenerateArticleRequest
from .database import Database
from .crud_endpoints import router as articles_router

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

# Include the CRUD router
app.include_router(articles_router)
router = APIRouter(prefix="/articles", tags=["tests"])

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

@app.post("/article/generate/{context}/{prompt}/{article_type}/{tone}/{committee}", response_model=None)
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

@app.get("/debug/transcript/{youtube_id}", response_model=None)
async def debug_transcript_endpoint(youtube_id: str) -> Dict[str, Any]:
    """
    Debug endpoint to inspect the raw transcript data structure.
    
    Args:
        youtube_id (str): YouTube video ID to debug
    
    Returns:
        Dict containing debug information about the transcript data
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Fetch raw transcript
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(youtube_id)
        
        # Analyze the structure
        debug_info = {
            "youtube_id": youtube_id,
            "transcript_type": str(type(transcript)),
            "transcript_length": len(transcript) if transcript else 0,
            "is_list": isinstance(transcript, list),
            "is_dict": isinstance(transcript, dict),
        }
        
        if transcript and len(transcript) > 0:
            first_entry = transcript[0]
            debug_info.update({
                "first_entry_type": str(type(first_entry)),
                "first_entry_attributes": dir(first_entry),
                "first_entry_str": str(first_entry),
                "first_entry_repr": repr(first_entry),
            })
            
            # Try to access common attributes
            if hasattr(first_entry, 'text'):
                debug_info["has_text_attribute"] = True
                debug_info["text_value"] = first_entry.text
            else:
                debug_info["has_text_attribute"] = False
                
            if isinstance(first_entry, dict):
                debug_info["is_dict_like"] = True
                debug_info["dict_keys"] = list(first_entry.keys()) if hasattr(first_entry, 'keys') else []
            else:
                debug_info["is_dict_like"] = False
        
        return debug_info
        
    except Exception as e:
        return {
            "error": str(e),
            "youtube_id": youtube_id,
            "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else "No traceback"
        }

@app.get("/debug/database", response_model=None)
async def debug_database_endpoint() -> Dict[str, Any]:
    """
    Debug endpoint to inspect the database directly.
    
    Returns:
        Dict containing database information and contents
    """
    try:
        if not database:
            return {"error": "Database not initialized"}
        
        # Get database info
        db_info = {
            "database_path": database.db_path,
            "is_connected": database.is_connected,
            "file_exists": False,
            "file_size": 0,
            "tables": [],
            "transcript_count": 0,
            "transcripts": []
        }
        
        # Check if database file exists
        import os
        if os.path.exists(database.db_path):
            db_info["file_exists"] = True
            db_info["file_size"] = os.path.getsize(database.db_path)
            
            # Get table info
            fresh_conn = sqlite3.connect(database.db_path)
            fresh_cursor = fresh_conn.cursor()
            
            try:
                # Get all tables
                fresh_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in fresh_cursor.fetchall()]
                db_info["tables"] = tables
                
                # Get transcript count
                if "transcripts" in tables:
                    fresh_cursor.execute("SELECT COUNT(*) FROM transcripts")
                    count = fresh_cursor.fetchone()[0]
                    db_info["transcript_count"] = count
                    
                    # Get sample transcripts
                    fresh_cursor.execute("SELECT id, title, date, LENGTH(content) as content_length FROM transcripts LIMIT 5")
                    transcripts = fresh_cursor.fetchall()
                    db_info["transcripts"] = [{"id": t[0], "title": t[1], "date": t[2], "content_length": t[3]} for t in transcripts]
                
            finally:
                fresh_cursor.close()
                fresh_conn.close()
        
        return db_info
        
    except Exception as e:
        return {
            "error": str(e),
            "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else "No traceback"
        }
