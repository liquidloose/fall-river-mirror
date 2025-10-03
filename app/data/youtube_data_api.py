import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


class YouTubeDataAPI:
    """YouTube Data API client for retrieving video metadata."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube Data API client.

        Args:
            api_key: YouTube Data API key. If not provided, will try to get from environment.
        """
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "YouTube API key is required. Set YOUTUBE_API_KEY environment variable."
            )

        self.base_url = "https://www.googleapis.com/youtube/v3"

    def get_video_published_date(self, youtube_id: str) -> Dict[str, Any]:
        """
        Get the published date for a YouTube video.

        Args:
            youtube_id: YouTube video ID (e.g., 'dQw4w9WgXcQ')

        Returns:
            Dict containing video metadata including published date

        Raises:
            Exception: If API call fails or video not found
        """
        try:
            # YouTube Data API endpoint for video details
            url = f"{self.base_url}/videos"

            params = {
                "part": "snippet,contentDetails",  # Get basic info + duration
                "id": youtube_id,
                "key": self.api_key,
            }

            logger.info(f"Making YouTube Data API request for video: {youtube_id}")
            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # Check if video was found
            if not data.get("items"):
                raise Exception(f"Video with ID '{youtube_id}' not found")

            video_info = data["items"][0]["snippet"]
            content_details = data["items"][0]["contentDetails"]

            # Extract published date (ISO 8601 format)
            published_at = video_info["publishedAt"]

            # Parse the date string to datetime object
            published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            # Extract and parse duration (ISO 8601 format like PT19M3S)
            duration_iso = content_details["duration"]

            # Convert ISO 8601 duration to seconds
            def parse_duration(duration_str):
                import re

                pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
                match = re.match(pattern, duration_str)
                if not match:
                    return 0
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                return hours * 3600 + minutes * 60 + seconds

            duration_seconds = parse_duration(duration_iso)

            # Format duration as readable string (e.g., "19:03" or "1:23:45")
            def format_duration(total_seconds):
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    return f"{minutes}:{seconds:02d}"

            duration_formatted = format_duration(duration_seconds)

            result = {
                "youtube_id": youtube_id,
                "published_at": published_at,
                "published_date": published_date,
                "title": video_info["title"],
                "channel_title": video_info["channelTitle"],
                "description": video_info.get("description", ""),
                "thumbnail_url": video_info["thumbnails"]["default"]["url"],
                "duration_iso": duration_iso,
                "duration_seconds": duration_seconds,
                "duration_formatted": duration_formatted,
            }

            logger.info(
                f"Successfully retrieved video info for {youtube_id}, published: {published_at}"
            )
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"YouTube Data API request failed: {str(e)}")
            raise Exception(f"Failed to fetch video data: {str(e)}")
        except KeyError as e:
            logger.error(f"Unexpected API response format: {str(e)}")
            raise Exception(f"Invalid API response format: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting video published date: {str(e)}")
            raise
