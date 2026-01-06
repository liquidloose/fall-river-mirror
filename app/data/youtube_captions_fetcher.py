"""
YouTube Data API v3 Captions Fetcher

This module provides functionality to fetch captions/transcripts from YouTube videos
using the official YouTube Data API v3 captions endpoints. This is the compliant way
to access YouTube captions according to YouTube's Terms of Service.

Requirements:
    - OAuth 2.0 credentials (handled by youtube_oauth module)
    - YouTube Data API v3 enabled in Google Cloud Console

API Documentation:
    https://developers.google.com/youtube/v3/docs/captions/list
    https://developers.google.com/youtube/v3/docs/captions/download

Example Usage:
    >>> from youtube_captions_fetcher import YouTubeCaptionsFetcher
    >>> fetcher = YouTubeCaptionsFetcher()
    >>> transcript = fetcher.get_transcript("dQw4w9WgXcQ")
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .youtube_oauth import YouTubeOAuth

logger = logging.getLogger(__name__)


class YouTubeCaptionsFetcher:
    """
    Fetches captions/transcripts from YouTube videos using YouTube Data API v3.

    This class uses the official YouTube Data API v3 captions endpoints to fetch
    captions in a compliant manner. It handles OAuth authentication, caption listing,
    downloading, and parsing various caption formats (SRT, VTT, TTML).
    """

    def __init__(self, oauth: Optional[YouTubeOAuth] = None):
        """
        Initialize YouTube captions fetcher.

        Args:
            oauth: YouTubeOAuth instance. If not provided, creates a new instance.
                   Note: OAuth credentials are obtained lazily when first needed,
                   not during initialization, to avoid blocking startup in Docker.

        Raises:
            Exception: If OAuth credentials path is invalid
        """
        if oauth is None:
            oauth = YouTubeOAuth()
        self.oauth = oauth
        self.youtube = None  # Lazy initialization - will be created on first use
        logger.info(
            "YouTube captions fetcher initialized (OAuth will be obtained on first use)"
        )

    def _ensure_youtube_client(self):
        """
        Ensure YouTube API client is initialized with OAuth credentials.
        Called lazily when first needed.

        Raises:
            Exception: If OAuth credentials cannot be obtained
        """
        if self.youtube is not None:
            return

        try:
            logger.info(
                "Obtaining OAuth credentials and initializing YouTube API client..."
            )
            credentials = self.oauth.get_credentials()
            self.youtube = build("youtube", "v3", credentials=credentials)
            logger.info("YouTube Data API v3 client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize YouTube API client: {str(e)}")
            raise

    def list_captions(self, video_id: str) -> List[Dict[str, Any]]:
        """
        List available caption tracks for a video.

        Args:
            video_id: YouTube video ID

        Returns:
            List of caption track dictionaries, each containing:
            - id: Caption track ID
            - snippet: Dictionary with language, name, etc.

        Raises:
            HttpError: If API request fails
        """
        self._ensure_youtube_client()
        try:
            logger.debug(f"Listing captions for video: {video_id}")
            request = self.youtube.captions().list(part="snippet", videoId=video_id)
            response = request.execute()

            items = response.get("items", [])
            logger.info(f"Found {len(items)} caption track(s) for video {video_id}")
            return items
        except HttpError as e:
            logger.error(f"Failed to list captions for video {video_id}: {str(e)}")
            raise

    def download_caption(self, caption_id: str, tfmt: str = "srt") -> str:
        """
        Download a caption track in the specified format.

        Args:
            caption_id: Caption track ID from list_captions()
            tfmt: Format ('srt', 'vtt', 'ttml', 'sbv'). Default: 'srt'

        Returns:
            Raw caption text in the specified format

        Raises:
            HttpError: If API request fails
        """
        self._ensure_youtube_client()
        try:
            logger.debug(f"Downloading caption {caption_id} in format {tfmt}")
            request = self.youtube.captions().download(id=caption_id, tfmt=tfmt)
            # Execute and decode the response
            caption_data = request.execute()

            # If response is bytes, decode to string
            if isinstance(caption_data, bytes):
                caption_text = caption_data.decode("utf-8")
            else:
                caption_text = str(caption_data)

            logger.debug(f"Downloaded caption {caption_id} ({len(caption_text)} chars)")
            return caption_text
        except HttpError as e:
            logger.error(f"Failed to download caption {caption_id}: {str(e)}")
            raise

    def _parse_srt(self, srt_text: str) -> List[Dict[str, Any]]:
        """
        Parse SRT (SubRip) format captions into list of snippets.

        Args:
            srt_text: Raw SRT caption text

        Returns:
            List of dictionaries with 'text', 'start', 'duration' keys
        """
        snippets = []
        # SRT format: sequence number, time range, text, blank line
        pattern = r"(\d+)\s*\n(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*\n(.*?)(?=\n\d+\s*\n|\n*$)"

        for match in re.finditer(pattern, srt_text, re.DOTALL):
            start_h, start_m, start_s, start_ms = map(int, match.groups()[1:5])
            end_h, end_m, end_s, end_ms = map(int, match.groups()[5:9])
            text = match.group(10).strip().replace("\n", " ")

            start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
            end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
            duration = end_time - start_time

            snippets.append({"text": text, "start": start_time, "duration": duration})

        return snippets

    def _parse_vtt(self, vtt_text: str) -> List[Dict[str, Any]]:
        """
        Parse VTT (WebVTT) format captions into list of snippets.

        Args:
            vtt_text: Raw VTT caption text

        Returns:
            List of dictionaries with 'text', 'start', 'duration' keys
        """
        snippets = []
        # VTT format: time range, text
        pattern = r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*\n(.*?)(?=\n\n|\n*\d{2}:\d{2}:\d{2}|\Z)"

        for match in re.finditer(pattern, vtt_text, re.DOTALL):
            start_h, start_m, start_s, start_ms = map(int, match.groups()[0:4])
            end_h, end_m, end_s, end_ms = map(int, match.groups()[4:8])
            text = match.group(9).strip().replace("\n", " ")

            start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
            end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
            duration = end_time - start_time

            snippets.append({"text": text, "start": start_time, "duration": duration})

        return snippets

    def _parse_ttml(self, ttml_text: str) -> List[Dict[str, Any]]:
        """
        Parse TTML (Timed Text Markup Language) format captions.

        Args:
            ttml_text: Raw TTML caption text

        Returns:
            List of dictionaries with 'text', 'start', 'duration' keys
        """
        snippets = []
        # TTML format: <p begin="..." end="...">text</p>
        pattern = r'<p begin="([^"]+)" end="([^"]+)">(.*?)</p>'

        def parse_time(time_str: str) -> float:
            # TTML time format: HH:MM:SS.mmm or HH:MM:SS
            parts = time_str.split(":")
            if len(parts) == 3:
                h, m, s = map(float, parts)
                return h * 3600 + m * 60 + s
            return 0.0

        for match in re.finditer(pattern, ttml_text, re.DOTALL):
            start_str, end_str, text = match.groups()
            start_time = parse_time(start_str)
            end_time = parse_time(end_str)
            duration = end_time - start_time

            # Clean HTML tags from text
            text = re.sub(r"<[^>]+>", "", text).strip()

            snippets.append({"text": text, "start": start_time, "duration": duration})

        return snippets

    def get_transcript(self, video_id: str, language: str = "en") -> Dict[str, Any]:
        """
        Get transcript for a video in JSON format matching the existing structure.

        This method:
        1. Lists available caption tracks
        2. Prefers manually created captions over auto-generated
        3. Downloads and parses the caption
        4. Returns in the same format as the old scraping implementation

        Args:
            video_id: YouTube video ID
            language: Preferred language code (default: 'en')

        Returns:
            Dictionary with:
            - snippets: List of caption snippets with text, start, duration
            - video_id: Video ID
            - language: Language code
            - language_code: Language code (duplicate for compatibility)
            - is_generated: Whether captions are auto-generated

        Raises:
            Exception: If no captions found or download fails
        """
        try:
            # List available caption tracks
            caption_tracks = self.list_captions(video_id)

            if not caption_tracks:
                raise Exception(f"No caption tracks found for video {video_id}")

            # Prefer manually created captions, then auto-generated
            # Also prefer the requested language
            preferred_track = None
            fallback_track = None

            for track in caption_tracks:
                snippet = track.get("snippet", {})
                track_language = snippet.get("language", "")
                is_auto_generated = (
                    snippet.get("trackKind") == "ASR"
                )  # Automatic Speech Recognition

                # Prefer manually created in requested language
                if track_language == language and not is_auto_generated:
                    preferred_track = track
                    break
                # Fallback to auto-generated in requested language
                elif track_language == language and fallback_track is None:
                    fallback_track = track
                # Or any manually created track
                elif not is_auto_generated and preferred_track is None:
                    preferred_track = track

            # Use preferred track, or fallback, or first available
            selected_track = preferred_track or fallback_track or caption_tracks[0]
            caption_id = selected_track["id"]
            snippet = selected_track.get("snippet", {})
            is_generated = snippet.get("trackKind") == "ASR"
            track_language = snippet.get("language", language)

            logger.info(
                f"Selected caption track {caption_id} (language: {track_language}, "
                f"generated: {is_generated}) for video {video_id}"
            )

            # Download caption (try SRT first, fallback to other formats)
            caption_text = None
            caption_format = None
            last_error = None
            has_forbidden_error = False
            for fmt in ["srt", "vtt", "ttml"]:
                try:
                    caption_text = self.download_caption(caption_id, fmt)
                    caption_format = fmt
                    break
                except HttpError as e:
                    last_error = e
                    # Check if it's a 403 Forbidden error (permissions issue)
                    if e.resp.status == 403:
                        has_forbidden_error = True
                        logger.debug(
                            f"403 Forbidden error downloading caption in {fmt} format: {str(e)}"
                        )
                    else:
                        logger.debug(
                            f"Failed to download caption in {fmt} format: {str(e)}"
                        )
                    continue

            if not caption_text:
                # Include "forbidden" in error message if we encountered 403 errors
                # This allows the fallback handler to catch it and use Whisper
                error_msg = (
                    f"Failed to download caption {caption_id} in any supported format"
                )
                if has_forbidden_error:
                    error_msg = f"Forbidden: {error_msg}. The permissions associated with the request are not sufficient to download the caption track. This typically means the video is not owned by the authenticated user. YouTube Data API v3 only allows downloading captions for videos you own."
                raise Exception(error_msg)

            # Parse caption based on format
            if caption_format == "srt":
                snippets = self._parse_srt(caption_text)
            elif caption_format == "vtt":
                snippets = self._parse_vtt(caption_text)
            elif caption_format == "ttml":
                snippets = self._parse_ttml(caption_text)
            else:
                raise Exception(f"Unsupported caption format: {caption_format}")

            logger.info(
                f"Successfully parsed {len(snippets)} caption snippets for video {video_id}"
            )

            # Return in format matching existing implementation
            return {
                "snippets": snippets,
                "video_id": video_id,
                "language": track_language,
                "language_code": track_language,
                "is_generated": is_generated,
            }

        except HttpError as e:
            error_msg = f"YouTube API error for video {video_id}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Failed to get transcript for video {video_id}: {str(e)}")
            raise
