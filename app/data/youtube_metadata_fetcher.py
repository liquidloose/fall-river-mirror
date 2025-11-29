"""
YouTube Data API Integration Module

This module provides a client for interacting with the YouTube Data API v3 to fetch
comprehensive video metadata including statistics, duration, and custom parsed fields.

The module uses direct HTTP requests (via the `requests` library) rather than the
official Google API client library for simplicity and minimal dependencies.

Key Features:
    - Fetch video metadata (title, description, channel, thumbnails)
    - Get video statistics (view count, like count, comment count)
    - Parse video duration from ISO 8601 format to seconds and readable format
    - Extract custom fields from meeting video titles (date, committee name)

Requirements:
    - YouTube Data API v3 key from Google Cloud Console
    - Set YOUTUBE_API_KEY environment variable or pass key to constructor

API Documentation:
    https://developers.google.com/youtube/v3/docs/videos/list

Example Usage:
    >>> from youtube_metadata_fetcher import YouTubeMetadataFetcher
    >>> fetcher = YouTubeMetadataFetcher()  # Uses YOUTUBE_API_KEY env var
    >>> metadata = fetcher.get_video_published_date("dQw4w9WgXcQ")
    >>> print(f"Title: {metadata['title']}")
    >>> print(f"Views: {metadata['view_count']:,}")
    >>> print(f"Duration: {metadata['duration_formatted']}")
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import requests
import re

logger = logging.getLogger(__name__)


class YouTubeMetadataFetcher:
    """
    YouTube metadata fetcher using the YouTube Data API v3.

    This class uses direct HTTP requests to the YouTube Data API v3 to fetch
    comprehensive video information including:
    - Basic metadata (title, description, channel, thumbnails)
    - Content details (duration, definition)
    - Statistics (view count, like count, comment count)
    - Custom parsed fields (meeting date from title, committee name)

    API Documentation: https://developers.google.com/youtube/v3/docs/videos/list

    Requires:
        A valid YouTube Data API key from Google Cloud Console:
        https://console.cloud.google.com/apis/credentials
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube metadata fetcher.

        Args:
            api_key: YouTube Data API v3 key. If not provided, attempts to read
                    from YOUTUBE_API_KEY environment variable.

        Raises:
            ValueError: If no API key is provided or found in environment.

        Example:
            >>> fetcher = YouTubeMetadataFetcher(api_key="YOUR_API_KEY")
            >>> # Or using environment variable:
            >>> fetcher = YouTubeMetadataFetcher()  # Reads from YOUTUBE_API_KEY env var
        """
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "YouTube API key is required. Set YOUTUBE_API_KEY environment variable or pass api_key parameter."
            )

        self.base_url = "https://www.googleapis.com/youtube/v3"
        logger.info("YouTubeMetadataFetcher initialized successfully")

    def get_video_published_date(self, youtube_id: str) -> Dict[str, Any]:
        """
        Fetch comprehensive metadata for a YouTube video using the Data API v3.

        This method retrieves video information including basic details, duration,
        statistics, and custom parsed fields specific to meeting videos.

        Args:
            youtube_id: The 11-character YouTube video ID (e.g., 'dQw4w9WgXcQ').
                       This is the ID portion from URLs like youtube.com/watch?v=dQw4w9WgXcQ

        Returns:
            Dict[str, Any]: A dictionary containing:
                - youtube_id (str): The video ID
                - published_at (str): ISO 8601 formatted publish date
                - published_date (datetime): Parsed datetime object
                - title (str): Video title
                - channel_title (str): Channel name
                - description (str): Video description
                - thumbnail_url (str): Default thumbnail URL
                - duration_iso (str): Duration in ISO 8601 format (e.g., "PT19M3S")
                - duration_seconds (int): Total duration in seconds
                - duration_formatted (str): Human-readable duration (e.g., "19:03")
                - view_count (int): Total video views
                - like_count (int): Total likes
                - comment_count (int): Total comments
                - meeting_date (str | None): Parsed date from title (MM-DD-YYYY format)
                - committee (str): Parsed committee name from title

        Raises:
            ValueError: If API key is missing
            requests.exceptions.RequestException: If API request fails
            Exception: If video not found or response format is unexpected

        Example:
            >>> fetcher = YouTubeMetadataFetcher()
            >>> metadata = fetcher.get_video_published_date("dQw4w9WgXcQ")
            >>> print(f"Views: {metadata['view_count']}")
            >>> print(f"Duration: {metadata['duration_formatted']}")
        """
        try:
            # ========================================
            # Step 1: Make API Request
            # ========================================
            # YouTube Data API v3 endpoint for video details
            url = f"{self.base_url}/videos"

            # API parameters
            # - part: Specifies which resource properties to include in response
            #   - snippet: Basic details (title, description, channel, thumbnails)
            #   - contentDetails: Duration, definition, dimension
            #   - statistics: View/like/comment counts
            # - id: The video ID to fetch
            # - key: Your API key for authentication
            params = {
                "part": "snippet,contentDetails,statistics",
                "id": youtube_id,
                "key": self.api_key,
            }

            logger.info(f"Making YouTube Data API request for video: {youtube_id}")
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx, 5xx)

            data = response.json()

            # ========================================
            # Step 2: Validate Response
            # ========================================
            # YouTube API returns empty 'items' array if video not found
            if not data.get("items"):
                raise Exception(f"Video with ID '{youtube_id}' not found")

            # Extract the three main data sections from API response
            video_info = data["items"][0]["snippet"]  # Basic metadata
            content_details = data["items"][0]["contentDetails"]  # Duration info
            statistics = data["items"][0].get(
                "statistics", {}
            )  # View/like/comment counts

            # ========================================
            # Step 3: Extract and Parse Published Date
            # ========================================
            # YouTube returns dates in ISO 8601 format: "2024-01-15T14:30:00Z"
            published_at = video_info["publishedAt"]

            # Convert ISO 8601 string to Python datetime object
            # Replace 'Z' (UTC indicator) with timezone-aware '+00:00'
            published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            # ========================================
            # Step 4: Parse Video Duration
            # ========================================
            # YouTube returns duration in ISO 8601 format (e.g., "PT19M3S" = 19 minutes, 3 seconds)
            # Format: PT[hours]H[minutes]M[seconds]S (all parts optional)
            # Examples: "PT1H23M45S" (1:23:45), "PT19M3S" (19:03), "PT45S" (0:45)
            duration_iso = content_details["duration"]

            def parse_duration(duration_str):
                """
                Convert ISO 8601 duration to total seconds.

                Args:
                    duration_str: ISO 8601 duration (e.g., "PT1H23M45S")

                Returns:
                    int: Total duration in seconds

                Examples:
                    "PT19M3S" -> 1143 seconds (19*60 + 3)
                    "PT1H23M45S" -> 5025 seconds (1*3600 + 23*60 + 45)
                """
                # Regex pattern matches: PT, optional hours (H), optional minutes (M), optional seconds (S)
                pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
                match = re.match(pattern, duration_str)
                if not match:
                    return 0

                # Extract hours, minutes, seconds (default to 0 if not present)
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)

                # Convert everything to seconds
                return hours * 3600 + minutes * 60 + seconds

            duration_seconds = parse_duration(duration_iso)

            def format_duration(total_seconds):
                """
                Format seconds into human-readable duration string.

                Args:
                    total_seconds: Total duration in seconds

                Returns:
                    str: Formatted duration (e.g., "19:03" or "1:23:45")

                Examples:
                    1143 -> "19:03"
                    5025 -> "1:23:45"
                    45 -> "0:45"
                """
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                # Include hours only if video is 1+ hours long
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    return f"{minutes}:{seconds:02d}"

            duration_formatted = format_duration(duration_seconds)

            # ========================================
            # Step 5: Parse Custom Fields from Video Title
            # ========================================
            # For meeting videos with titles like "11.5.2025 City Council Meeting"
            # Extract: meeting_date (11-05-2025) and committee (City Council Meeting)

            # Match date pattern at start of title: "M.D.YYYY" or "MM.DD.YYYY"
            date_match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", video_info["title"])

            # Convert from "11.5.2025" format to "11-05-2025" format (zero-padded)
            # If no date match in title, fall back to YouTube published date
            if date_match:
                meeting_date = f"{date_match.group(1).zfill(2)}-{date_match.group(2).zfill(2)}-{date_match.group(3)}"
            else:
                # Format published_date to MM-DD-YYYY format
                meeting_date = published_date.strftime("%m-%d-%Y")

            # Remove date prefix from title to get committee name
            # "11.5.2025 City Council Meeting" -> "City Council Meeting"
            committee = re.sub(r"^\d{1,2}\.\d{1,2}\.\d{4}\s+", "", video_info["title"])

            # ========================================
            # Step 6: Build Result Dictionary
            # ========================================
            result = {
                # Video Identification
                "youtube_id": youtube_id,
                # Timestamps
                "published_at": published_at,  # ISO 8601 string (e.g., "2024-01-15T14:30:00Z")
                "published_date": published_date,  # Python datetime object
                # Basic Metadata
                "title": video_info["title"],  # Full video title
                "channel_title": video_info["channelTitle"],  # Channel name
                "description": video_info.get(
                    "description", ""
                ),  # Video description (can be empty)
                "thumbnail_url": video_info["thumbnails"]["default"][
                    "url"
                ],  # Default thumbnail URL
                # Duration (multiple formats for convenience)
                "duration_iso": duration_iso,  # ISO 8601 format (e.g., "PT19M3S")
                "duration_seconds": duration_seconds,  # Total seconds (e.g., 1143)
                "duration_formatted": duration_formatted,  # Human-readable (e.g., "19:03")
                # Statistics (engagement metrics)
                # Note: Some videos may have statistics disabled, default to 0
                "view_count": int(statistics.get("viewCount", 0)),  # Total views
                "like_count": int(statistics.get("likeCount", 0)),  # Total likes
                "comment_count": int(
                    statistics.get("commentCount", 0)
                ),  # Total comments
                # Custom Parsed Fields (specific to meeting videos)
                "meeting_date": meeting_date,  # Parsed from title (MM-DD-YYYY) or None
                "committee": committee,  # Committee name extracted from title
            }

            logger.info(
                f"Successfully retrieved video info for {youtube_id} | "
                f"Title: '{video_info['title']}' | "
                f"Published: {published_at} | "
                f"Duration: {duration_formatted} | "
                f"Views: {result['view_count']:,} | "
                f"Likes: {result['like_count']:,} | "
                f"Comments: {result['comment_count']:,}"
            )
            return result

        # ========================================
        # Exception Handling
        # ========================================
        except requests.exceptions.RequestException as e:
            # Network errors, HTTP errors (401 Unauthorized, 403 Forbidden, 404 Not Found, etc.)
            # Common causes:
            # - Invalid API key (401/403)
            # - Rate limit exceeded (429)
            # - Network connectivity issues
            # - YouTube API service outage (5xx)
            logger.error(f"YouTube Data API request failed: {str(e)}")
            raise Exception(f"Failed to fetch video data from YouTube API: {str(e)}")

        except KeyError as e:
            # Missing expected fields in API response
            # This can happen if:
            # - YouTube changes their API response format
            # - Video has unusual privacy settings
            # - Required fields are missing from the response
            logger.error(f"Unexpected API response format, missing key: {str(e)}")
            raise Exception(f"Invalid API response format - missing field: {str(e)}")

        except Exception as e:
            # Catch-all for any other unexpected errors
            # (parsing errors, datetime conversion errors, etc.)
            logger.error(f"Unexpected error while getting video metadata: {str(e)}")
            raise
