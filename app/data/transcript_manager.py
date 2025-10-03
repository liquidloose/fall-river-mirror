from datetime import datetime
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
from .data_classes import AIAgent, Committee
from ..ai.whisper_processor import WhisperProcessor
from .youtube_data_api import YouTubeDataAPI

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Manages YouTube transcript operations including fetching, caching, and database operations."""

    def __init__(self, committee: str, database=None):
        self.committee = committee
        self.database = database
        self.category = AIAgent.GROK

    # =============================================================================
    # PUBLIC API METHODS
    # =============================================================================

    def get_transcript(
        self,
        committee: Committee,
        youtube_id: str = "VjaU4DAxP6s",
    ) -> Dict[str, Any] | JSONResponse:
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
            if self._is_transcript_cached(youtube_id):
                return self._get_cached_transcript(youtube_id)

            # If not in database, fetch from YouTube
            logger.info(
                f"Transcript for video {youtube_id} not found in database, fetching from YouTube..."
            )

            # Fetch rich data object with transcript and video metadata
            rich_data = self._fetch_from_youtube(youtube_id)
            transcript = rich_data["transcript"]  # Extract transcript string
            video_metadata = rich_data["video_metadata"]  # Extract metadata

            # Store transcript in database if available
            if self._can_cache():
                logger.info(
                    f"Caching transcript for video {youtube_id} with category {self.category}"
                )
                self._cache_transcript(
                    youtube_id, transcript, committee, video_metadata
                )

            return self._formatted_youtube_response(
                youtube_id, transcript, video_metadata
            )

        except Exception as e:
            logger.error(f"Failed to get transcript from YouTube {youtube_id}")
            logger.error(f"Failed to get transcript from YouTube: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
            )

    # =============================================================================
    # DATABASE CACHE METHODS
    # =============================================================================

    def _get_cached_transcript(self, video_id: str) -> Dict[str, Any]:
        """Retrieve transcript from database cache."""
        logger.info(f"Transcript for video {video_id} found in database cache")
        transcript_data = self.database.get_transcript_by_youtube_id(video_id)

        if not transcript_data:
            raise Exception("Transcript data not found in database")

        # Return the transcript content from the database
        content = transcript_data[3]  # content is at index 3
        logger.info(
            f"Successfully retrieved transcript for video {video_id} from database"
        )

        all_transcripts = self._get_all_transcripts_info()

        return {
            "status": "healthy",
            "message": "Transcript retrieved from database cache",
            "source": "database_cache",
            "category": transcript_data[5],
            "youtube_id": video_id,
            "transcript_id": transcript_data[0],
            "content": content,
            "cached_at": transcript_data[4],  # fetch_date is at index 4
            "database_path": self.database.db_path,
            "database_contents": {
                "total_transcripts": len(all_transcripts),
                "all_transcripts": all_transcripts,
            },
            "category": all_transcripts,
        }

    def _cache_transcript(
        self,
        youtube_id: str,
        content: str,
        committee: object = Committee.BOARD_OF_HEALTH,
        video_metadata: Dict[str, Any] = None,
    ) -> int:
        """
        Add a YouTube transcript to the database.

        Args:
            youtube_id: YouTube video ID
            content: Full transcript content
            committee: Committee name (default: "YouTube")
            category: Transcript category (default: "Video Transcript")

        Returns:
            int: The ID of the newly created transcript
        """
        operation_details = {
            "youtube_id": youtube_id,
            "committee": committee,
            "category": f"{self.category.value} Transcript",
            "content_length": len(content),
        }
        logger.info(f"add_youtube_transcript: {operation_details}")

        try:
            youtube_id = youtube_id
            fetch_date = datetime.now().isoformat()

            # Debug: Log the database path and operation details
            logger.info(f"Adding transcript to database: {self.database.db_path}")
            logger.info(f"youtube_id: {youtube_id}")
            logger.info(f"Content length: {len(content)}")
            logger.info(f"fetch_Date: {fetch_date}")

            # Create a fresh connection for this operation to avoid threading issues
            fresh_conn = sqlite3.connect(self.database.db_path)
            fresh_cursor = fresh_conn.cursor()

            try:
                # Debug: Check if table exists
                fresh_cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'"
                )
                table_exists = fresh_cursor.fetchone()
                logger.info(f"Transcripts table exists: {table_exists is not None}")

                if not table_exists:
                    logger.error("Transcripts table does not exist!")
                    # Let the Database class handle table creation with proper schema
                    logger.info("Creating transcripts table using Database class...")
                    fresh_cursor.close()
                    fresh_conn.close()

                    # Create a new Database instance to avoid connection issues
                    if self.database:
                        from .database import Database

                        temp_db = Database(self.database.db_path)
                        temp_db._create_all_tables()
                        temp_db.close()
                        logger.info(
                            "Transcripts table created successfully via Database class"
                        )
                    else:
                        logger.error(
                            "No database instance available for table creation"
                        )
                        return transcript_id

                    # Reconnect after table creation
                    fresh_conn = sqlite3.connect(self.database.db_path)
                    fresh_cursor = fresh_conn.cursor()

                logger.info(f"NewCategory: {self.category}")
                # Now insert the transcript
                logger.info(
                    f"Inserting transcript into database: {committee}, {youtube_id}, content_length: {len(content)}, {fetch_date}, {self.category}"
                )

                api_key = os.getenv("YOUTUBE_API_KEY")

                yt_data = YouTubeDataAPI(api_key).get_video_published_date(youtube_id)
                yt_published_date = yt_data[
                    "published_at"
                ]  # Extract just the date string

                # Extract video metadata if available
                video_title = yt_data.get("title", "") if yt_data else ""
                video_duration_seconds = (
                    yt_data.get("duration_seconds", 0) if yt_data else 0
                )
                video_duration_formatted = (
                    yt_data.get("duration_formatted", "") if yt_data else ""
                )
                video_channel = yt_data.get("channel_title", "") if yt_data else ""
                video_description = yt_data.get("description", "") if yt_data else ""

                fresh_cursor.execute(
                    """INSERT INTO transcripts 
                    (committee, youtube_id, content, yt_published_date, fetch_date, model,
                     video_title, video_duration_seconds, video_duration_formatted, 
                     video_channel, video_description) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        committee,
                        youtube_id,
                        content,
                        yt_published_date,
                        fetch_date,
                        self.category,
                        video_title,
                        video_duration_seconds,
                        video_duration_formatted,
                        video_channel,
                        video_description,
                    ),
                )
                fresh_conn.commit()

                # Log successful insertion with video metadata
                logger.info(
                    f"Successfully inserted transcript with video metadata: "
                    f"title='{video_title}', duration={video_duration_formatted}, "
                    f"channel='{video_channel}', published={yt_published_date}"
                )

                # Verify the insert worked
                fresh_cursor.execute(
                    "SELECT COUNT(*) FROM transcripts WHERE youtube_id LIKE ?",
                    (f"%{youtube_id}%",),
                )
                count = fresh_cursor.fetchone()[0]
                logger.info(f"Transcripts in database after insert: {count}")

                transcript_id = fresh_cursor.lastrowid
                logger.info(
                    f"Added YouTube t ranscript for video '{youtube_id}' (ID: {transcript_id})"
                )
                return transcript_id
            finally:
                fresh_cursor.close()
                fresh_conn.close()

        except Exception as e:
            logger.error(
                f"add_youtube_transcript error: {e}, details: {operation_details}"
            )
            raise

    # =============================================================================
    # YOUTUBE API METHODS
    # =============================================================================

    def _fetch_from_youtube(self, youtube_id: str) -> Dict[str, Any]:
        """
        Fetch transcript and video metadata from YouTube APIs.

        Returns a rich data object containing both transcript and video metadata.
        First attempts to get transcript via YouTube Transcript API.
        If that fails, downloads the video and uses OpenAI Whisper API.

        Returns:
            Dict containing transcript, video metadata (title, duration, date, etc.)
        """
        # First try YouTube Transcript API
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_data = ytt_api.fetch(youtube_id)
            logger.info(
                f"Successfully fetched transcript for video: {youtube_id} data: {transcript_data}"
            )
            # Convert FetchedTranscript object to stringified dict
            import json

            transcript_dict = {
                "snippets": [
                    {
                        "text": snippet.text,
                        "start": snippet.start,
                        "duration": snippet.duration,
                    }
                    for snippet in transcript_data.snippets
                ],
                "video_id": transcript_data.video_id,
                "language": transcript_data.language,
                "language_code": transcript_data.language_code,
                "is_generated": transcript_data.is_generated,
            }

            # Fetch video metadata (title, duration, published date, etc.)
            video_metadata = None
            try:
                api_key = os.getenv("YOUTUBE_API_KEY")
                if api_key:
                    from .youtube_data_api import YouTubeDataAPI

                    youtube_api = YouTubeDataAPI(api_key)
                    video_metadata = youtube_api.get_video_published_date(youtube_id)
                    logger.info(
                        f"Retrieved video metadata for {youtube_id}: {video_metadata['title']}"
                    )
            except Exception as e:
                logger.warning(f"Could not fetch video metadata: {str(e)}")
                video_metadata = None

            # Return rich data object
            return {
                "transcript": json.dumps(transcript_dict),
                "video_metadata": video_metadata,
                "source": "youtube_transcript_api",
            }
        except (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            CouldNotRetrieveTranscript,
        ) as e:
            logger.warning(
                f"YouTube Transcript API failed for video {youtube_id}: {str(e)}"
            )
            logger.info(
                f"Attempting fallback to OpenAI Whisper for video: {youtube_id}"
            )

            # change the value of the category that's stored in state management
            print("changing self.category from", self.category)
            logger.info(f"Changing state.category to: {self.category}")

            # Fallback to OpenAI Whisper
            return self._fetch_via_whisper(youtube_id)

    # =============================================================================
    # OPENAI WHISPER API METHODS
    # =============================================================================

    def _fetch_via_whisper(self, video_id: str) -> str:
        """
        Download video and transcribe using OpenAI Whisper API.
        """

        whisper_processor = WhisperProcessor(video_id=video_id)

        self.category = AIAgent.WHISPER

        logger.info(
            f"Transcribing video {video_id} with self.category.value: {self.category.value}"
        )
        return whisper_processor.transcribe_youtube_video(video_id)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _can_cache(self) -> bool:
        """Check if database is available for caching."""
        return self.database and self.database.is_connected

    def _is_transcript_cached(self, video_id: str) -> bool:
        """Check if transcript exists in database cache."""
        if not self._can_cache():
            logger.warning("Database not available, skipping cache check")
            return False

        return self.database.transcript_exists_by_youtube_id(video_id)

    def _get_all_transcripts_info(self) -> list:
        """Get information about all transcripts in the database."""
        all_transcripts = []
        try:
            if not self.database:
                return all_transcripts

            fresh_conn = sqlite3.connect(self.database.db_path)
            fresh_cursor = fresh_conn.cursor()
            fresh_cursor.execute(
                "SELECT id, youtube_id, fetch_date, LENGTH(content) as content_length FROM transcripts ORDER BY id"
            )
            all_transcripts = [
                {
                    "id": row[0],
                    "youtube_id": row[1],
                    "fetch_date": row[2],
                    "content_length": row[3],
                }
                for row in fresh_cursor.fetchall()
            ]
            fresh_cursor.close()
            fresh_conn.close()
        except Exception as e:
            logger.warning(f"Could not fetch all transcripts: {str(e)}")

        return all_transcripts

    def _formatted_youtube_response(
        self, youtube_id: str, transcript: str, video_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Format response for transcript fetched from YouTube with video metadata."""
        all_transcripts = self._get_all_transcripts_info()

        response = {
            "message": ("Youtube Transcript fetched already cached in the database"),
            "model": self.category.value,
            "source": "YouTube Data API",
            "youtube_id": youtube_id,
            "transcript": transcript,
            "database_path": self.database.db_path if self.database else "No database",
            "database_contents": {
                "total_transcripts": len(all_transcripts),
                "all_transcripts": all_transcripts,
            },
        }

        # Add video metadata if available
        if video_metadata:
            response["video"] = {
                "title": video_metadata.get("title", "Unknown"),
                "duration": video_metadata.get("duration_formatted", "Unknown"),
                "duration_seconds": video_metadata.get("duration_seconds", 0),
                "published_date": video_metadata.get("published_at", "Unknown"),
                "channel": video_metadata.get("channel_title", "Unknown"),
                "youtube_id": video_metadata.get("youtube_id", youtube_id),
            }

        return response
