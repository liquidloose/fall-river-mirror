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
                "part": "snippet",  # Get basic video info including publish date
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

            # Extract published date (ISO 8601 format)
            published_at = video_info["publishedAt"]

            # Parse the date string to datetime object
            published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            result = {
                "youtube_id": youtube_id,
                "published_at": published_at,
                "published_date": published_date,
                "title": video_info["title"],
                "channel_title": video_info["channelTitle"],
                "description": video_info.get("description", ""),
                "thumbnail_url": video_info["thumbnails"]["default"]["url"],
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
