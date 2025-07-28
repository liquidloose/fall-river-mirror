# Standard library imports
from datetime import datetime
from enum import Enum
import logging

# Third-party imports
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

# Local imports
from app.utils import read_context_file
from .xai_classes import XAIProcessor 
from .data_classes import ArticleType, Tone
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
def health_check():
    """
    Health check endpoint to verify the server is running.
    
    Returns:
        dict: Status message indicating server is operational
    """
    logger.info("Health check endpoint called!")
    return {"status": "ok", "message": "Server is running"}


@app.get("/article/writer/{context}/{prompt}")
def read_root(
    context: str,
    prompt: str,
    article_type: ArticleType = ArticleType.SUMMARY,
    tone: Tone = Tone.FORMAL,
):
    """
    Main article writing endpoint that generates content based on context and parameters.
    
    Args:
        context (str): The base context for the article
        prompt (str): The user's specific writing prompt
        article_type (ArticleType): Type of article to generate (default: SUMMARY)
        tone (Tone): Writing tone to use (default: FORMAL)
    
    Returns:
        dict: Generated article content from the XAI processor
    """
    # Build context based on article type
    # Add specific context files for different article types
    match article_type:
        case ArticleType.OP_ED:
            final_context = context + read_context_file("article_types", "op_ed.txt")
        case ArticleType.SUMMARY:
            final_context = context + read_context_file("article_types", "summary.txt")

    # Build context based on tone
    # Add specific context files for different writing tones
    match tone:
        case Tone.FRIENDLY:
            final_context = final_context + read_context_file("tone", "friendly.txt")
        case Tone.PROFESSIONAL:
            final_context = final_context + read_context_file("tone", "professional.txt")
        case Tone.CASUAL:
            final_context = final_context + read_context_file("tone", "casual.txt")
        case Tone.FORMAL:
            final_context = final_context + read_context_file("tone", "formal.txt")

    # Log the request details for debugging
    logger.info(
        f"Received request: context={context},final_context={final_context}, prompt={prompt}, type={article_type}, tone={tone}"
    )
    
    # Initialize XAI processor and create the full prompt
    xai_processor = XAIProcessor()
    full_prompt = f"This is the type of article: {article_type.value} This is the tone: {tone.value} This is the context: {context}. This is the user's prompt: {prompt}"
    logger.info(f"Full prompt: {full_prompt}")
    
    # Generate response using the XAI processor
    response = xai_processor.get_response(final_context, full_prompt)
    logger.debug(f"Response: {response}")
    return response


@app.get("/experiments/")
def get_transcript(video_id: str = "VjaU4DAxP6s"):
    """
    Experimental endpoint to fetch YouTube video transcripts.
    
    Args:
        video_id (str): YouTube video ID (default: "VjaU4DAxP6s")
    
    Returns:
        dict: YouTube transcript data or error response
    """
    try:
        # Initialize YouTube Transcript API and fetch transcript
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
    except Exception as e:
        # Return error response if transcript fetching fails
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
        )

    return transcript
