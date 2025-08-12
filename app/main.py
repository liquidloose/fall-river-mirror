# Standard library imports
from datetime import datetime
from enum import Enum
import logging
from typing import Dict, Any

# Third-party imports
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

# Local imports
from app.utils import read_context_file, get_transcript, write_article, yt_crawler
from .xai_processor import XAIProcessor 
from .data_classes import ArticleType, Committee, Tone
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

# Initialize FastAPI application and XAI processor
app = FastAPI()
database = Database("fr-mirror")
xai_processor = XAIProcessor()
logger.info("FastAPI app initialized!")

@app.get("/")
def health_check() -> Dict[str, str]:
    """
    Health check endpoint to verify the server is running.
    
    Returns:
        dict: Status message indicating server is operational
    """
    logger.info("Health check endpoint called!")
    return {"status": "ok", "message": "Server is running"}

@app.get("/create/transcript/{youtube_id=VjaU4DAxP6s}", response_model=None)
def get_transcript_endpoint(youtube_id: str = "VjaU4DAxP6s") -> Dict[str, Any] | JSONResponse:
    """
    Experimental endpoint to fetch YouTube video transcripts.
    
    Args:
        video_id (str): YouTube video ID (default: "VjaU4DAxP6s")
    
    Returns:
        Dict[str, Any] | JSONResponse: YouTube transcript data or error response
    """
    return get_transcript(youtube_id)


@app.get("/write/article/{context}/{prompt}/{article_type}/{tone}/{committee}", response_model=None)
def write_article_endpoint(
    context: str,
    prompt: str,
    article_type: ArticleType,
    tone: Tone,
    committee: Committee,
) -> Dict[str, Any] | JSONResponse:
    """
    Main article writing endpoint that generates content based on context and parameters.
    
    Args:
        context (str): The base context for the article
        prompt (str): The user's specific writing prompt
        article_type (ArticleType): Type of article to generate
        tone (Tone): Writing tone to use
        committee (Committee): Committee type for the article
    
    Returns:
        Dict[str, Any] | JSONResponse: Generated article content from the XAI processor or error response
    """
    return write_article(context, prompt, article_type, tone, committee)


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
    return yt_crawler(video_id)
