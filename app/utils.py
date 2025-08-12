import os
import textwrap
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from .xai_processor import XAIProcessor
from .data_classes import ArticleType, Tone, Committee

logger = logging.getLogger(__name__)


def get_transcript(video_id: str = "VjaU4DAxP6s"):
    """
    Fetch YouTube video transcript using the YouTube Transcript API.
    
    Args:
        video_id (str): YouTube video ID (default: "VjaU4DAxP6s")
    
    Returns:
        YouTube transcript data or error response
    """
    try:
        # Initialize YouTube Transcript API and fetch transcript
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        logger.info(f"Successfully fetched transcript for video: {video_id}")
        return transcript
    except Exception as e:
        # Return error response if transcript fetching fails
        logger.error(f"Failed to get transcript from YouTube for video {video_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
        )


def read_context_file(subdir: str, filename: str) -> str:
    """
    Read content from a context file in the specified subdirectory.
    
    This function reads text content from context files stored in the app/context_files/
    directory structure. Context files typically contain prompts, instructions, or
    configuration text that can be used with AI processors.
    
    Args:
        subdir (str): The subdirectory within context_files/ where the file is located.
                      For example: "sentiment", "analysis", "prompts"
        filename (str): The name of the file to read, including extension.
                       For example: "sentiment_analyzer.txt", "prompt_template.txt"
    
    Returns:
        str: The content of the file as a string, with leading/trailing whitespace removed.
             Returns "default" if the file is not found.
    
    Raises:
        FileNotFoundError: If the specified file does not exist in the expected location.
                          This is caught and logged, then "default" is returned.
    
    Example:
        >>> content = read_context_file("sentiment", "analyzer_prompt.txt")
        >>> print(content)
        "Analyze the sentiment of the following text..."
        
        >>> # File structure:
        >>> # app/
        >>> #   context_files/
        >>> #     sentiment/
        >>> #       analyzer_prompt.txt
        >>> #     analysis/
        >>> #       summary_prompt.txt
    
    Note:
        - Files are expected to be in UTF-8 encoding
        - The function automatically strips leading/trailing whitespace
        - If the file is not found, it logs an error and returns "default"
        - This allows for graceful fallback when context files are missing
    """
    try:
        # Construct the full file path
        filepath = os.path.join("app", "context_files", subdir, filename)
        
        # Read the file content with UTF-8 encoding
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read().strip()
            logger.info(f"Successfully loaded context file: {filepath}")
            return content
            
    except FileNotFoundError:
        logger.error(f"Context file not found: {filepath}")
        logger.warning(f"Returning 'default' for missing file: {subdir}/{filename}")
        return "default"
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode file {filepath} with UTF-8 encoding: {e}")
        return "default"
    except Exception as e:
        logger.error(f"Unexpected error reading file {filepath}: {e}")
        return "default"


def write_article(
    context: str,
    prompt: str,
    article_type: ArticleType,
    tone: Tone,
    committee: Committee,
) -> Dict[str, Any] | JSONResponse:
    """
    Generate article content based on context and parameters.
    
    Args:
        context (str): The base context for the article
        prompt (str): The user's specific writing prompt
        article_type (ArticleType): Type of article to generate
        tone (Tone): Writing tone to use
        committee (Committee): Committee type for the article
    
    Returns:
        Dict[str, Any] | JSONResponse: Generated article content or error response
    """
    try:
        # Build context based on article type
        final_context = _build_article_context(context, article_type)
        
        # Build context based on tone
        final_context = _build_tone_context(final_context, tone)
        
        # Log the request details for debugging
        logger.info(
            f"Processing article: type={article_type}, tone={tone}, committee={committee}"
        )
        
        # Initialize XAI processor and create the full prompt
        xai_processor = XAIProcessor()
        full_prompt = f"This is the type of article: {article_type.value} This is the tone: {tone.value} This is the context: {context}. This is the user's prompt: {prompt}"
        logger.info(f"Full prompt: {full_prompt}")
        
        # Generate response using the XAI processor
        response = xai_processor.get_response(
            final_context, 
            full_prompt, 
            committee.value,
            article_type.value,
            tone.value
        )
        logger.debug(f"Response generated successfully")
        return response
        
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate article: {str(e)}"},
        )


def _build_article_context(context: str, article_type: ArticleType) -> str:
    """Build context based on article type."""
    final_context = context
    match article_type:
        case ArticleType.OP_ED:
            final_context = context + read_context_file("article_types", "op_ed.txt")
        case ArticleType.SUMMARY:
            final_context = context + read_context_file("article_types", "summary.txt")
    return final_context


def _build_tone_context(context: str, tone: Tone) -> str:
    """Build context based on writing tone."""
    final_context = context
    match tone:
        case Tone.FRIENDLY:
            final_context = context + read_context_file("tone", "friendly.txt")
        case Tone.PROFESSIONAL:
            final_context = context + read_context_file("tone", "professional.txt")
        case Tone.CASUAL:
            final_context = context + read_context_file("tone", "casual.txt")
        case Tone.FORMAL:
            final_context = context + read_context_file("tone", "formal.txt")
    return final_context


def yt_crawler(video_id: str) -> Dict[str, Any] | JSONResponse:
    """
    YouTube crawler function that processes video transcripts and generates articles.
    
    Args:
        video_id (str): YouTube video ID to crawl
    
    Returns:
        Dict[str, Any] | JSONResponse: Combined data from transcript and processing
    """
    try:
        # Get transcript for the video
        transcript_result = get_transcript(video_id)
        
        # Check if transcript was successful
        if isinstance(transcript_result, JSONResponse):
            return transcript_result
        
        # Create a context from the transcript
        transcript_text = str(transcript_result)[:1000]  # Limit to first 1000 chars for context
        
        # Generate article from transcript
        article_result = write_article(
            context=f"YouTube video {video_id} transcript: {transcript_text}",
            prompt="Create a comprehensive summary of this YouTube video transcript",
            article_type=ArticleType.SUMMARY,
            tone=Tone.FORMAL,
            committee=Committee.PLANNING_BOARD
        )
        
        # Combine the data
        result = {
            "video_id": video_id,
            "transcript": transcript_result,
            "article": article_result,
            "crawled_at": datetime.now().isoformat()
        }
        
        logger.info(f"Successfully crawled video {video_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error in yt_crawler for video {video_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to crawl video {video_id}: {str(e)}"}
        )
