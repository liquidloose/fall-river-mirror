import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import os
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from .create_database import Database

logger = logging.getLogger(__name__)


class VideoQueueManager:
    """
    Manages the video processing queue by discovering new YouTube videos and tracking them.

    This class:
    1. Queries existing transcripts to avoid duplicates
    2. Uses YouTube API to discover video IDs from channels
    3. Compares and adds only new videos to the queue

    Uses YouTube Data API v3 and SQLite for queue management.
    """

    def __init__(self, database: Database):
        """
        Initialize the queue manager with a database connection.

        Args:
            database: Database instance for managing transcripts and queue (required)
        """
        self.database = database
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            logger.warning(
                "YOUTUBE_API_KEY not found in environment variables. "
                "API calls will fail. Get a free key at: "
                "https://console.cloud.google.com/apis/credentials"
            )
        self.base_url = "https://www.googleapis.com/youtube/v3"

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass  # No cleanup needed for API-based approach

    def get_existing_youtube_ids(self) -> Set[str]:
        """
        Query transcripts table and get all youtube_ids that already have transcripts.

        Returns:
            Set of youtube_id strings that already exist in the database
        """
        if not self.database:
            logger.error("No database connection available")
            return set()

        try:
            cursor = self.database.cursor
            cursor.execute(
                "SELECT youtube_id FROM transcripts WHERE youtube_id IS NOT NULL"
            )
            results = cursor.fetchall()

            existing_ids = {row[0] for row in results if row[0]}
            logger.info(f"Found {len(existing_ids)} existing transcripts in database")
            return existing_ids

        except Exception as e:
            logger.error(f"Failed to query existing youtube_ids: {str(e)}")
            return set()

    def get_queued_youtube_ids(self) -> Set[str]:
        """
        Query video_queue table and get all youtube_ids already in the queue.

        Returns:
            Set of youtube_id strings that are already in the video_queue
        """
        if not self.database:
            logger.error("No database connection available")
            return set()

        try:
            cursor = self.database.cursor
            cursor.execute(
                "SELECT youtube_id FROM video_queue WHERE youtube_id IS NOT NULL"
            )
            results = cursor.fetchall()

            queued_ids = {row[0] for row in results if row[0]}
            logger.info(f"Found {len(queued_ids)} videos already in queue")
            return queued_ids

        except Exception as e:
            logger.error(f"Failed to query queued youtube_ids: {str(e)}")
            return set()

    def _extract_channel_info(self, channel_url: str) -> Optional[Dict[str, str]]:
        """
        Extract channel ID or handle from a YouTube URL.

        Args:
            channel_url: YouTube channel URL

        Returns:
            Dict with 'type' and 'value' or None
        """
        # Pattern: youtube.com/@handle
        handle_match = re.search(r"youtube\.com/@([^/\?]+)", channel_url)
        if handle_match:
            return {"type": "handle", "value": handle_match.group(1)}

        # Pattern: youtube.com/channel/CHANNEL_ID
        channel_match = re.search(r"youtube\.com/channel/([^/\?]+)", channel_url)
        if channel_match:
            return {"type": "id", "value": channel_match.group(1)}

        # Pattern: youtube.com/c/CustomName
        custom_match = re.search(r"youtube\.com/c/([^/\?]+)", channel_url)
        if custom_match:
            return {"type": "custom", "value": custom_match.group(1)}

        logger.error(f"Could not extract channel info from URL: {channel_url}")
        return None

    def _get_channel_id(self, channel_info: Dict[str, str]) -> Optional[str]:
        """
        Get the channel ID from various channel identifiers.

        Args:
            channel_info: Dict with 'type' and 'value'

        Returns:
            Channel ID or None
        """
        if not self.api_key:
            logger.error("Cannot get channel ID without API key")
            return None

        if channel_info["type"] == "id":
            return channel_info["value"]

        # For handles and custom URLs, we need to look up the channel ID
        try:
            if channel_info["type"] == "handle":
                response = requests.get(
                    f"{self.base_url}/channels",
                    params={
                        "part": "id",
                        "forHandle": channel_info["value"],
                        "key": self.api_key,
                    },
                    timeout=10,
                )
            else:  # custom name
                response = requests.get(
                    f"{self.base_url}/search",
                    params={
                        "part": "snippet",
                        "q": channel_info["value"],
                        "type": "channel",
                        "maxResults": 1,
                        "key": self.api_key,
                    },
                    timeout=10,
                )

            response.raise_for_status()
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                if channel_info["type"] == "handle":
                    return data["items"][0]["id"]
                else:
                    return data["items"][0]["id"]["channelId"]

            logger.error(f"No channel found for {channel_info}")
            return None

        except Exception as e:
            logger.error(f"Failed to get channel ID: {str(e)}")
            return None

    async def scrape_youtube_ids(
        self, channel_url: str, max_limit: int = 100, scroll_count: int = 5
    ) -> List[str]:
        """
        Get video IDs from a YouTube channel using the YouTube API.

        Args:
            channel_url: URL of the YouTube channel
            max_limit: Maximum number of video IDs to extract (0 = all videos)
            scroll_count: Ignored (kept for API compatibility)

        Returns:
            List of YouTube video IDs discovered from the channel
        """
        logger.info(f"Fetching video IDs from: {channel_url}")

        if not self.api_key:
            raise Exception(
                "YOUTUBE_API_KEY not set. Get a free key at: "
                "https://console.cloud.google.com/apis/credentials"
            )

        video_ids = []

        try:
            # Extract channel info from URL
            channel_info = self._extract_channel_info(channel_url)
            if not channel_info:
                raise Exception(f"Invalid YouTube channel URL: {channel_url}")

            # Get channel ID
            channel_id = self._get_channel_id(channel_info)
            if not channel_id:
                raise Exception(f"Could not find channel ID for: {channel_url}")

            logger.info(f"Found channel ID: {channel_id}")

            # Get the "uploads" playlist ID for this channel
            channel_response = requests.get(
                f"{self.base_url}/channels",
                params={
                    "part": "contentDetails",
                    "id": channel_id,
                    "key": self.api_key,
                },
                timeout=10,
            )
            channel_response.raise_for_status()
            channel_data = channel_response.json()

            if "items" not in channel_data or len(channel_data["items"]) == 0:
                raise Exception(f"Channel not found: {channel_id}")

            uploads_playlist_id = channel_data["items"][0]["contentDetails"][
                "relatedPlaylists"
            ]["uploads"]
            logger.info(f"Uploads playlist ID: {uploads_playlist_id}")

            # Fetch all videos from the uploads playlist
            next_page_token = None

            while True:
                playlist_params = {
                    "part": "contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": 50,  # API max per request
                    "key": self.api_key,
                }

                if next_page_token:
                    playlist_params["pageToken"] = next_page_token

                playlist_response = requests.get(
                    f"{self.base_url}/playlistItems",
                    params=playlist_params,
                    timeout=10,
                )
                playlist_response.raise_for_status()
                playlist_data = playlist_response.json()

                # Extract video IDs
                for item in playlist_data.get("items", []):
                    video_id = item["contentDetails"]["videoId"]
                    video_ids.append(video_id)

                logger.info(
                    f"Fetched {len(video_ids)} videos so far from {channel_url}"
                )

                # Check if we've hit the limit (0 means no limit)
                if max_limit > 0 and len(video_ids) >= max_limit:
                    video_ids = video_ids[:max_limit]
                    logger.info(f"Reached max_limit of {max_limit} videos")
                    break

                # Check for next page
                next_page_token = playlist_data.get("nextPageToken")
                if not next_page_token:
                    logger.info(f"No more pages. Total videos: {len(video_ids)}")
                    break

            logger.info(f"Extracted {len(video_ids)} unique video IDs")
            return video_ids

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise Exception(f"YouTube API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching video IDs: {str(e)}")
            raise

    async def queue_new_videos(
        self, channel_url: str, max_limit: int = 100, scroll_count: int = 5
    ) -> Dict[str, Any]:
        """
        Compare fetched IDs with existing data and add only new videos to the queue.

        This method:
        1. Gets all existing youtube_ids from transcripts table
        2. Gets all youtube_ids already in video_queue table
        3. Fetches video IDs from YouTube API
        4. For each discovered video:
           - Skip if already has transcript
           - Skip if already in queue
           - Add to queue only if both checks pass

        Args:
            channel_url: URL of the YouTube channel to scrape
            max_limit: Maximum number of videos to process (0 = all videos)
            scroll_count: Ignored (kept for API compatibility)

        Returns:
            Dict containing results:
                - total_discovered: Number of videos found on YouTube
                - already_exists: Number of videos that already have transcripts
                - already_in_queue: Number of videos already in the queue
                - newly_queued: Number of videos actually added to queue (new rows)
                - skipped: Number of videos skipped (already exist or in queue)
                - failed: Number of videos that failed to process
                - youtube_ids: List of all discovered IDs
        """
        logger.info(f"Starting queue_new_videos for: {channel_url}")

        results = {
            "total_discovered": 0,
            "already_exists": 0,
            "already_in_queue": 0,
            "newly_queued": 0,
            "skipped": 0,
            "failed": 0,
            "youtube_ids": [],
        }

        try:
            # Step 1: Get existing youtube_ids from transcripts table
            existing_ids = self.get_existing_youtube_ids()
            logger.info(f"Found {len(existing_ids)} existing transcripts")

            # Step 2: Get youtube_ids already in the queue
            queued_ids = self.get_queued_youtube_ids()
            logger.info(f"Found {len(queued_ids)} videos already in queue")

            # Step 3: Fetch video IDs from YouTube API
            scraped_ids = await self.scrape_youtube_ids(
                channel_url, max_limit, scroll_count
            )
            results["total_discovered"] = len(scraped_ids)
            results["youtube_ids"] = scraped_ids

            logger.info(f"Discovered {len(scraped_ids)} videos on YouTube")

            # Step 4: Compare and add new videos to queue
            for youtube_id in scraped_ids:
                try:
                    # Check 1: If video ID exists in transcripts, skip it
                    if youtube_id in existing_ids:
                        logger.debug(
                            f"Skipping {youtube_id} - transcript already exists"
                        )
                        results["already_exists"] += 1
                        results["skipped"] += 1
                    # Check 2: If video ID already in queue, skip it
                    elif youtube_id in queued_ids:
                        logger.debug(f"Skipping {youtube_id} - already in queue")
                        results["already_in_queue"] += 1
                        results["skipped"] += 1
                    # Add to queue only if both checks pass
                    else:
                        if self._add_to_queue(youtube_id):
                            logger.info(f"Added {youtube_id} to video queue")
                            results["newly_queued"] += 1
                            # Update queued_ids set so we don't try to add it again in this run
                            queued_ids.add(youtube_id)
                        else:
                            # This should rarely happen now since we check before adding
                            logger.warning(f"Failed to add {youtube_id} to queue")
                            results["failed"] += 1

                except Exception as e:
                    logger.error(f"Error processing video ID {youtube_id}: {str(e)}")
                    results["failed"] += 1

            logger.info(
                f"Queue processing complete: {results['total_discovered']} discovered, "
                f"{results['already_exists']} already have transcripts, "
                f"{results['already_in_queue']} already in queue, "
                f"{results['newly_queued']} newly queued, "
                f"{results['skipped']} skipped, {results['failed']} failed"
            )

            return results

        except Exception as e:
            logger.error(f"Failed to queue new videos: {str(e)}")
            raise

    def _check_captions(self, youtube_id: str) -> bool:
        """
        Check if transcripts are available for a video WITHOUT downloading the full transcript.

        This method uses youtube-transcript-api to check if ANY transcript exists for a video,
        including both manually uploaded closed captions AND auto-generated captions.

        Why this approach:
        - Lightweight: Only checks availability, doesn't download content
        - Fast: Single API call to YouTube
        - Comprehensive: Detects both manual and auto-generated transcripts
        - Reliable: Uses the same library we'll use for actual transcript fetching

        Use case:
        This prevents expensive/slow Whisper processing during bulk operations.
        Videos with transcript_available=1 can be processed fast with YouTube's API.
        Videos with transcript_available=0 will need Whisper (slow, requires audio download).

        Args:
            youtube_id: The 11-character YouTube video ID (e.g., 'dQw4w9WgXcQ')

        Returns:
            bool: True if at least one transcript is available, False otherwise

        Exceptions handled:
            - TranscriptsDisabled: Video owner disabled transcripts
            - NoTranscriptFound: No transcripts exist for this video
            - VideoUnavailable: Video is private, deleted, or doesn't exist
            - Exception: Catch-all for rate limits, network errors, etc.
        """
        try:
            api = YouTubeTranscriptApi()
            api.list(youtube_id)
            logger.debug(f"Video {youtube_id}: transcript available")
            return True
        except (TranscriptsDisabled, NoTranscriptFound):
            logger.debug(f"Video {youtube_id}: no transcript available")
            return False
        except VideoUnavailable:
            logger.warning(f"Video {youtube_id}: video unavailable")
            return False
        except Exception as e:
            logger.error(f"Video {youtube_id}: error checking transcript: {str(e)}")
            return False

    def _add_to_queue(self, youtube_id: str) -> bool:
        """
        Add a YouTube video ID to the video_queue table.

        Args:
            youtube_id: YouTube video ID to queue

        Returns:
            True if successfully added (new row created), False if already exists or failed
        """
        if not self.database:
            logger.error("Cannot add to queue - no database connection")
            return False

        try:
            # Check if transcript is actually available (manual or auto-generated)
            has_transcript = self._check_captions(youtube_id)

            self.database.cursor.execute(
                """INSERT OR IGNORE INTO video_queue 
                   (youtube_id, transcript_available) 
                   VALUES (?, ?)""",
                (youtube_id, 1 if has_transcript else 0),
            )
            self.database.conn.commit()

            # Check if a row was actually inserted
            # rowcount will be 0 if INSERT OR IGNORE skipped due to existing row
            was_inserted = self.database.cursor.rowcount > 0

            if was_inserted:
                if has_transcript:
                    logger.info(f"Added {youtube_id} to queue (transcript available)")
                else:
                    logger.info(
                        f"Added {youtube_id} to queue (no transcript - will require Whisper)"
                    )
            else:
                logger.debug(f"Skipped {youtube_id} - already in queue")

            return was_inserted

        except Exception as e:
            logger.error(f"Failed to add {youtube_id} to queue: {str(e)}")
            return False

    def get_queue_stats(self) -> Dict[str, int]:
        """
        Get statistics about the current video queue.

        Returns:
            Dict with queue statistics
        """
        if not self.database:
            return {"error": "No database connection"}

        try:
            cursor = self.database.cursor

            # Total in queue
            cursor.execute("SELECT COUNT(*) FROM video_queue")
            total = cursor.fetchone()[0]

            # With transcripts available
            cursor.execute(
                "SELECT COUNT(*) FROM video_queue WHERE transcript_available = 1"
            )
            available = cursor.fetchone()[0]

            # Without transcripts
            cursor.execute(
                "SELECT COUNT(*) FROM video_queue WHERE transcript_available = 0"
            )
            pending = cursor.fetchone()[0]

            return {
                "total": total,
                "transcript_available": available,
                "pending": pending,
            }

        except Exception as e:
            logger.error(f"Failed to get queue stats: {str(e)}")
            return {"error": str(e)}

    async def close(self):
        """
        Close any resources.
        Kept for API compatibility but not needed for API-based approach.
        """
        logger.info("VideoQueueManager closed")
