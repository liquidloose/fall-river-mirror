import os
import tempfile
import logging
import shutil
import subprocess
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
import yt_dlp
from openai import OpenAI

from app.data_classes import Committee

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Manages YouTube transcript operations including fetching, caching, and database operations."""

    def __init__(self, committee: str, database=None):
        self.committee = committee
        self.database = database

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

    def _fetch_from_youtube(self, video_id: str) -> str:
        """
        Fetch transcript from YouTube API with OpenAI Whisper fallback.

        First attempts to get transcript via YouTube Transcript API.
        If that fails, downloads the video and uses OpenAI Whisper API.
        """
        # First try YouTube Transcript API
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id)
            logger.info(f"Successfully fetched transcript for video: {video_id}")
            return str(transcript)

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

    def _fetch_via_whisper(self, video_id: str) -> str:
        """
        Download video and transcribe using OpenAI Whisper API.
        """
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        if not client.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for Whisper fallback"
            )

        temp_dir = None

        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            audio_file_path = os.path.join(temp_dir, f"{video_id}.%(ext)s")

            # Download audio from YouTube video with compression
            ydl_opts = {
                "format": "bestaudio[filesize<25M]/best[filesize<25M]/bestaudio/best",
                "outtmpl": audio_file_path,
                "audioquality": "96K",  # Lower bitrate to reduce file size
                "noplaylist": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "96",
                    }
                ],
            }

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Downloading audio for video: {video_id}")
                ydl.download([youtube_url])

            # Find the actual downloaded file (yt-dlp changes extension)
            downloaded_files = [
                f for f in os.listdir(temp_dir) if f.startswith(video_id)
            ]
            if not downloaded_files:
                raise Exception("No audio file was downloaded")

            actual_audio_path = os.path.join(temp_dir, downloaded_files[0])

            # Check file size and split if needed
            file_size = os.path.getsize(actual_audio_path)
            max_size = 25 * 1024 * 1024  # 25MB in bytes

            if file_size > max_size:
                logger.info(
                    f"Audio file is {file_size / 1024 / 1024:.1f}MB, splitting into chunks"
                )
                transcript_text = self._transcribe_large_file(
                    client, actual_audio_path, video_id, temp_dir
                )
            else:
                logger.info(
                    f"Audio file is {file_size / 1024 / 1024:.1f}MB, transcribing directly"
                )
                # Transcribe using OpenAI Whisper
                logger.info(
                    f"Transcribing audio using OpenAI Whisper for video: {video_id}"
                )

                with open(actual_audio_path, "rb") as audio_file:
                    transcript_response = client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file, response_format="text"
                    )

                transcript_text = transcript_response
                logger.info(
                    f"Successfully transcribed video {video_id} using OpenAI Whisper"
                )

            return transcript_text

        except Exception as e:
            logger.error(
                f"Failed to transcribe video {video_id} using Whisper: {str(e)}"
            )
            raise Exception(
                f"Both YouTube Transcript API and Whisper fallback failed: {str(e)}"
            )

        finally:
            # Cleanup temporary files
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temporary directory: {cleanup_error}"
                    )

    def _transcribe_large_file(
        self, client: OpenAI, audio_path: str, video_id: str, temp_dir: str
    ) -> str:
        """Split large audio file into chunks and transcribe each chunk."""
        try:
            # Split audio into 20-minute chunks (1200 seconds) to stay well under 25MB
            chunk_duration = 1200  # seconds
            chunks = []

            # Get audio duration first
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            total_duration = float(result.stdout.strip())
            logger.info(f"Total audio duration: {total_duration:.1f} seconds")

            # Split into chunks
            chunk_count = 0
            for start_time in range(0, int(total_duration), chunk_duration):
                chunk_path = os.path.join(
                    temp_dir, f"{video_id}_chunk_{chunk_count}.mp3"
                )

                # Use FFmpeg to extract chunk
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        audio_path,
                        "-ss",
                        str(start_time),
                        "-t",
                        str(chunk_duration),
                        "-acodec",
                        "copy",
                        chunk_path,
                        "-y",
                    ],
                    check=True,
                    capture_output=True,
                )

                chunks.append(chunk_path)
                chunk_count += 1
                logger.info(
                    f"Created chunk {chunk_count}: {start_time}s-{start_time + chunk_duration}s"
                )

            # Transcribe each chunk
            all_transcripts = []
            for i, chunk_path in enumerate(chunks):
                logger.info(f"Transcribing chunk {i + 1}/{len(chunks)}")

                with open(chunk_path, "rb") as audio_file:
                    transcript_response = client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file, response_format="text"
                    )

                all_transcripts.append(transcript_response)
                logger.info(f"Completed chunk {i + 1}/{len(chunks)}")

            # Combine all transcripts
            full_transcript = " ".join(all_transcripts)
            logger.info(
                f"Successfully transcribed {len(chunks)} chunks for video {video_id}"
            )

            return full_transcript

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error while processing large file: {e}")
            raise Exception(f"Audio processing failed: {e}")
        except Exception as e:
            logger.error(f"Error transcribing large file: {e}")
            raise

    def _cache_transcript(self, video_id: str, transcript: str, committee: str):
        """Store transcript in database cache."""
        try:
            transcript_id = self.database.add_youtube_transcript(
                video_id, transcript, committee
            )
            logger.info(
                f"Successfully stored transcript for video {video_id} in database with ID: {transcript_id}"
            )
        except Exception as db_error:
            logger.warning(f"Failed to store transcript in database: {str(db_error)}")
            # Continue even if database storage fails

    def _format_youtube_response(
        self, video_id: str, transcript: str
    ) -> Dict[str, Any]:
        """Format response for transcript fetched from YouTube."""
        all_transcripts = self._get_all_transcripts_info()

        return {
            "message": (
                "Transcript fetched from YouTube and cached in the database"
                if self._can_cache()
                else "Transcript fetched from YouTube (database not available)"
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
