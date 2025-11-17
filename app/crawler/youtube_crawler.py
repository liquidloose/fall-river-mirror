import logging
from datetime import datetime
from typing import Dict, Any
from fastapi.responses import JSONResponse
from app.data.transcript_manager import TranscriptManager
from app.writing_department.article_generator import ArticleGenerator
from app.data.data_classes import ArticleType, Tone

logger = logging.getLogger(__name__)


class YouTubeCrawler:
    """Orchestrates the full workflow of crawling YouTube videos, getting transcripts, and generating articles."""

    def __init__(self, database=None):
        self.transcript_manager = TranscriptManager(database)
        self.article_generator = ArticleGenerator()

    def crawl_video(self, video_id: str) -> Dict[str, Any] | JSONResponse:
        """
        YouTube crawler function that processes video transcripts and generates articles.

        Args:
            video_id (str): YouTube video ID to crawl

        Returns:
            Dict[str, Any] | JSONResponse: Combined data from transcript and processing
        """
        try:
            # Get transcript for the video
            transcript_result = self.transcript_manager.get_transcript(video_id)

            # Check if transcript was successful
            if isinstance(transcript_result, JSONResponse):
                return transcript_result

            # Create a context from the transcript
            transcript_text = str(transcript_result)[
                :1000
            ]  # Limit to first 1000 chars for context

            # Generate article from transcript
            article_result = self.article_generator.write_article(
                context=f"YouTube video {video_id} transcript: {transcript_text}",
                prompt="Create a comprehensive summary of this YouTube video transcript",
                article_type=ArticleType.SUMMARY,
                tone=Tone.FORMAL,
                committee=str,
            )

            # Combine the data
            result = {
                "video_id": video_id,
                "transcript": transcript_result,
                "article": article_result,
                "crawled_at": datetime.now().isoformat(),
            }

            logger.info(f"Successfully crawled video {video_id}")
            return result

        except Exception as e:
            logger.error(f"Error in yt_crawler for video {video_id}: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to crawl video {video_id}: {str(e)}"},
            )

    def get_transcript_only(self, video_id: str) -> Dict[str, Any] | JSONResponse:
        """Get only the transcript for a video without generating an article."""
        return self.transcript_manager.get_transcript(video_id)

    def generate_article_only(
        self,
        context: str,
        prompt: str,
        article_type: ArticleType,
        tone: Tone,
        committee: str,
    ) -> Dict[str, Any] | JSONResponse:
        """Generate an article without transcript processing."""
        return self.article_generator.write_article(
            context, prompt, article_type, tone, committee
        )
