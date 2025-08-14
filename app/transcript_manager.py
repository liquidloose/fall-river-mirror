import os
import logging
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
import sqlite3

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Manages YouTube transcript operations including fetching, caching, and database operations."""
    
    def __init__(self, database=None):
        self.database = database
    
    def get_transcript(self, video_id: str = "VjaU4DAxP6s") -> Dict[str, Any] | JSONResponse:
        """
        Fetch YouTube video transcript using the YouTube Transcript API.
        First checks if transcript exists in database, if not fetches from YouTube and stores it.
        
        Args:
            video_id (str): YouTube video ID (default: "VjaU4DAxP6s")
        
        Returns:
            Dict containing transcript data with source information, or error response
        """
        try:
            # Check if transcript already exists in database
            if self._is_transcript_cached(video_id):
                return self._get_cached_transcript(video_id)
            
            # If not in database, fetch from YouTube
            logger.info(f"Transcript for video {video_id} not found in database, fetching from YouTube...")
            transcript = self._fetch_from_youtube(video_id)
            
            # Store transcript in database if available
            if self._can_cache():
                self._cache_transcript(video_id, transcript)
            
            return self._format_youtube_response(video_id, transcript)
            
        except Exception as e:
            logger.error(f"Failed to get transcript from YouTube {video_id}: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
            )
    
    def _is_transcript_cached(self, video_id: str) -> bool:
        """Check if transcript exists in database cache."""
        if not self._can_cache():
            logger.warning("Database not available, skipping cache check")
            return False
        
        return self.database.transcript_exists_by_youtube_id(video_id)
    
    def _get_cached_transcript(self, video_id: str) -> Dict[str, Any]:
        """Retrieve transcript from database cache."""
        logger.info(f"Transcript for video {video_id} found in database cache")
        transcript_data = self.database.get_transcript_by_youtube_id(video_id)
        
        if not transcript_data:
            raise Exception("Transcript data not found in database")
        
        # Return the transcript content from the database
        transcript_content = transcript_data[3]  # content is at index 3
        logger.info(f"Successfully retrieved transcript for video {video_id} from database")
        
        all_transcripts = self._get_all_transcripts_info()
        
        return {
            "status": "healthy",
            "message": "Transcript retrieved from database cache",
            "source": "database_cache",
            "youtube_id": video_id,
            "transcript_id": transcript_data[0],
            "content": transcript_content,
            "cached_at": transcript_data[4],  # date is at index 4
            "database_path": self.database.db_path,
            "database_contents": {
                "total_transcripts": len(all_transcripts),
                "all_transcripts": all_transcripts
            }
        }
    
    def _fetch_from_youtube(self, video_id: str) -> str:
        """Fetch transcript from YouTube API."""
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        logger.info(f"Successfully fetched transcript for video: {video_id}")
        return str(transcript)
    
    def _cache_transcript(self, video_id: str, transcript: str):
        """Store transcript in database cache."""
        try:
            transcript_id = self.database.add_youtube_transcript(video_id, transcript)
            logger.info(f"Successfully stored transcript for video {video_id} in database with ID: {transcript_id}")
        except Exception as db_error:
            logger.warning(f"Failed to store transcript in database: {str(db_error)}")
            # Continue even if database storage fails
    
    def _format_youtube_response(self, video_id: str, transcript: str) -> Dict[str, Any]:
        """Format response for transcript fetched from YouTube."""
        all_transcripts = self._get_all_transcripts_info()
        
        return {
            "message": "Transcript fetched from YouTube and cached in the database" if self._can_cache() else "Transcript fetched from YouTube (database not available)",
            "source": "youtube_api",
            "youtube_id": video_id,
            "transcript": transcript,
            "database_path": self.database.db_path if self.database else "No database",
            "database_contents": {
                "total_transcripts": len(all_transcripts),
                "all_transcripts": all_transcripts
            }
        }
    
    def _can_cache(self) -> bool:
        """Check if database is available for caching."""
        return self.database and self.database.is_connected
    
    def _get_all_transcripts_info(self) -> list:
        """Get information about all transcripts in the database."""
        all_transcripts = []
        try:
            if not self.database:
                return all_transcripts
                
            fresh_conn = sqlite3.connect(self.database.db_path)
            fresh_cursor = fresh_conn.cursor()
            fresh_cursor.execute("SELECT id, title, date, LENGTH(content) as content_length FROM transcripts ORDER BY id")
            all_transcripts = [{"id": row[0], "title": row[1], "date": row[2], "content_length": row[3]} for row in fresh_cursor.fetchall()]
            fresh_cursor.close()
            fresh_conn.close()
        except Exception as e:
            logger.warning(f"Could not fetch all transcripts: {str(e)}")
        
        return all_transcripts
