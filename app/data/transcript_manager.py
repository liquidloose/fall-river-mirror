import datetime
import os
import logging
from typing import Optional, Dict, Any, List
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
)
import sqlite3

from app.data_classes import AIAgent, Committee
from app.ai.whisper_processor import WhisperProcessor

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Manages YouTube transcript operations including fetching, caching, and database operations."""

    def __init__(self, committee: str, database=None):
        self.committee = committee
        self.database = database

    # =============================================================================
    # PUBLIC API METHODS
    # =============================================================================

    def get_transcript(
        self,
        committee: Committee,
        video_id: str = "VjaU4DAxP6s",
    ) -> Dict[str, Any] | JSONResponse:
        """
        Fetch YouTube video transcript using the YouTube Transcript API.
        First checks if transcript exists in database, if not fetches from YouTube and stores it.

        Args:
            video_id (str): YouTube video ID (default: "VjaU4DAxP6s")

        Returns:
            Dict containing transcript data with source information, or error response
        """
        # Set up logging
        self.logger = logging.getLogger(f"Database Transcript Manager")
        self.logger.setLevel(logging.INFO)

        try:
            # Check if transcript already exists in database
            if self._is_transcript_cached(video_id):
                return self._get_cached_transcript(video_id)

            # If not in database, fetch from YouTube
            logger.info(
                f"Transcript for video {video_id} not found in database, fetching from YouTube..."
            )
            transcript = self._fetch_from_youtube(video_id)

            # Store transcript in database if available
            if self._can_cache():
                self._cache_transcript(video_id, transcript, committee)

            return self._formatted_youtube_response(video_id, transcript)

        except Exception as e:
            logger.error(f"Failed to get transcript from YouTube {video_id}: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
            )

    # =============================================================================
    # DATABASE CACHE METHODS
    # =============================================================================

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
        logger.info(
            f"Successfully retrieved transcript for video {video_id} from database"
        )

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
                "all_transcripts": all_transcripts,
            },
        }

    # =============================================================================
    # YOUTUBE API METHODS
    # =============================================================================

    def _fetch_from_youtube(self, video_id: str) -> str:
        """
        Fetch transcript from YouTube API with OpenAI Whisper fallback.

        First attempts to get transcript via YouTube Transcript API.
        If that fails, downloads the video and uses OpenAI Whisper API.
        """
        # First try YouTube Transcript API
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_data = ytt_api.fetch(video_id)
            logger.info(f"Successfully fetched transcript for video: {video_id}")
            return transcript_data
        except (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            CouldNotRetrieveTranscript,
        ) as e:
            logger.warning(
                f"YouTube Transcript API failed for video {video_id}: {str(e)}"
            )
            logger.info(f"Attempting fallback to OpenAI Whisper for video: {video_id}")

            # Fallback to OpenAI Whisper
            return self._fetch_via_whisper(video_id)

        except Exception as e:
            logger.error(
                f"Unexpected error with YouTube Transcript API for video {video_id}: {str(e)}"
            )
            logger.info(f"Attempting fallback to OpenAI Whisper for video: {video_id}")

            # Fallback to OpenAI Whisper for any other errors
            return self._fetch_via_whisper(video_id)

    def _formatted_youtube_response(
        self, video_id: str, transcript: str
    ) -> Dict[str, Any]:
        """Format response for transcript fetched from YouTube."""
        all_transcripts = self._get_all_transcripts_info()

        return {
            "message": (
                "Youtube Transcript fetched already cached in the database"
                if self._can_cache()
                else "Transcript fetched from YouTube (this transcript is new)"
            ),
            "source": "youtube_api",
            "youtube_id": video_id,
            "transcript": transcript,
            "database_path": self.database.db_path if self.database else "No database",
            "database_contents": {
                "total_transcripts": len(all_transcripts),
                "all_transcripts": all_transcripts,
            },
        }

    # =============================================================================
    # OPENAI WHISPER METHODS
    # =============================================================================

    def _fetch_via_whisper(self, video_id: str) -> str:
        """
        Download video and transcribe using OpenAI Whisper API.
        """
        whisper_processor = WhisperProcessor(video_id=video_id)

        return whisper_processor.transcribe_youtube_video(video_id)

    # =============================================================================
    # DATABASE STORAGE METHODS
    # =============================================================================

    def _add_youtube_transcript(
        self,
        youtube_id: str,
        transcript_content: str,
        committee: object = Committee.BOARD_OF_HEALTH,
        category: object = AIAgent.GROK,
    ) -> int:
        """
        Add a YouTube transcript to the database.

        Args:
            youtube_id: YouTube video ID
            transcript_content: Full transcript content
            committee: Committee name (default: "YouTube")
            category: Transcript category (default: "Video Transcript")

        Returns:
            int: The ID of the newly created transcript
        """
        operation_details = {
            "youtube_id": youtube_id,
            "committee": committee,
            "category": f"{category} Transcript",
            "content_length": len(transcript_content),
        }
        self._log_operation("add_youtube_transcript", operation_details)

        try:
            title = youtube_id
            date = datetime.now().isoformat()

            # Debug: Log the database path and operation details
            self.logger.info(f"Adding transcript to database: {self.db_path}")
            self.logger.info(f"Title: {title}")
            self.logger.info(f"Content length: {len(transcript_content)}")
            self.logger.info(f"Date: {date}")

            # Create a fresh connection for this operation to avoid threading issues
            fresh_conn = sqlite3.connect(self.db_path)
            fresh_cursor = fresh_conn.cursor()

            try:
                # Debug: Check if table exists
                fresh_cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'"
                )
                table_exists = fresh_cursor.fetchone()
                self.logger.info(
                    f"Transcripts table exists: {table_exists is not None}"
                )

                if not table_exists:
                    self.logger.error("Transcripts table does not exist!")
                    # Create the table if it doesn't exist
                    self.logger.info("Creating transcripts table...")
                    fresh_cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS transcripts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            committee TEXT,
                            title TEXT,
                            content TEXT,
                            date TEXT,
                            category TEXT
                        )
                    """
                    )
                    fresh_conn.commit()
                    self.logger.info("Transcripts table created successfully")

                # Now insert the transcript
                self.logger.info(
                    f"Inserting transcript into database: {committee}, {title}, {transcript_content}, {date}, {category}"
                )
                fresh_cursor.execute(
                    "INSERT INTO transcripts (committee, title, content, date, category) VALUES (?, ?, ?, ?, ?)",
                    (committee, title, transcript_content, date, category),
                )
                fresh_conn.commit()

                # Verify the insert worked
                fresh_cursor.execute(
                    "SELECT COUNT(*) FROM transcripts WHERE title LIKE ?",
                    (f"%{youtube_id}%",),
                )
                count = fresh_cursor.fetchone()[0]
                self.logger.info(f"Transcripts in database after insert: {count}")

                transcript_id = fresh_cursor.lastrowid
                self.logger.info(
                    f"Added YouTube transcript for video '{youtube_id}' (ID: {transcript_id})"
                )
                return transcript_id
            finally:
                fresh_cursor.close()
                fresh_conn.close()

        except Exception as e:
            self._log_error("add_youtube_transcript", e, operation_details)
            raise

    def _cache_transcript(self, video_id: str, transcript: str, committee: str):
        """Store transcript in database cache."""
        try:
            transcript_id = self._add_youtube_transcript(
                video_id, transcript, committee
            )
            logger.info(
                f"Successfully stored transcript for video {video_id} in database with ID: {transcript_id}"
            )
        except Exception as db_error:
            logger.warning(f"Failed to store transcript in database: {str(db_error)}")
            # Continue even if database storage fails

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

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
            fresh_cursor.execute(
                "SELECT id, title, date, LENGTH(content) as content_length FROM transcripts ORDER BY id"
            )
            all_transcripts = [
                {
                    "id": row[0],
                    "title": row[1],
                    "date": row[2],
                    "content_length": row[3],
                }
                for row in fresh_cursor.fetchall()
            ]
            fresh_cursor.close()
            fresh_conn.close()
        except Exception as e:
            logger.warning(f"Could not fetch all transcripts: {str(e)}")

        return all_transcripts
