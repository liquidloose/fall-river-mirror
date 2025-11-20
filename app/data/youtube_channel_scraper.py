import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser
import re
from ..data.create_database import Database

logger = logging.getLogger(__name__)


class YouTubeChannelScraper:
    """
    Scrapes YouTube channel pages to discover video IDs and queues them for transcript fetching.

    This class uses Playwright to navigate YouTube pages, extract video IDs from thumbnails,
    checks if transcripts already exist, and adds missing IDs to a processing queue.
    """

    def __init__(self, database: Database):
        """
        Initialize the scraper with a database connection.

        Args:
            database: Database instance for checking existing transcripts and managing queue (required)
        """
        self.database = database
        self.playwright = sync_playwright().start()
        self.browser: Browser = self.playwright.chromium.launch(headless=True)
        self.page: Page = self.browser.new_page()

    def scrape_channel_archive(
        self, archive_url: str, max_videos: int = 100
    ) -> Dict[str, Any]:
        """
        Scrape YouTube channel archive page and queue missing transcripts.

        Args:
            archive_url: URL of the YouTube channel/playlist archive page
            max_videos: Maximum number of videos to process (default: 100)

        Returns:
            Dict containing scraping results and statistics
        """
        logger.info(f"Starting scrape of channel archive: {archive_url}")

        results = {
            "total_discovered": 0,
            "already_exists": 0,
            "newly_queued": 0,
            "failed": 0,
            "youtube_ids": [],
        }

        try:
            # Extract video IDs from the page
            video_ids = self._extract_video_ids_from_page(archive_url, max_videos)
            results["total_discovered"] = len(video_ids)
            results["youtube_ids"] = video_ids

            logger.info(f"Discovered {len(video_ids)} videos on page")

            # Process each video ID
            for youtube_id in video_ids:
                try:
                    # Check if transcript already exists
                    if self._transcript_exists(youtube_id):
                        logger.debug(f"Transcript already exists for {youtube_id}")
                        results["already_exists"] += 1
                    else:
                        # Add to queue if not exists
                        if self._add_to_queue(youtube_id, archive_url):
                            logger.info(f"Added {youtube_id} to transcript queue")
                            results["newly_queued"] += 1
                        else:
                            logger.warning(f"Failed to queue {youtube_id}")
                            results["failed"] += 1

                except Exception as e:
                    logger.error(f"Error processing video ID {youtube_id}: {str(e)}")
                    results["failed"] += 1

            logger.info(
                f"Scraping complete: {results['total_discovered']} discovered, "
                f"{results['already_exists']} exist, {results['newly_queued']} queued, "
                f"{results['failed']} failed"
            )

            return results

        except Exception as e:
            logger.error(f"Failed to scrape channel archive: {str(e)}")
            raise

    def _extract_video_ids_from_page(self, url: str, max_videos: int) -> List[str]:
        """
        Use Playwright to load page and extract YouTube video IDs from thumbnails.

        Args:
            url: YouTube page URL to scrape
            max_videos: Maximum number of video IDs to extract

        Returns:
            List of YouTube video IDs
        """
        video_ids = []

        try:
            logger.info(f"Loading page: {url}")
            self.page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for video thumbnails to load
            self.page.wait_for_selector("a#video-title", timeout=10000)

            # Scroll to load more videos (YouTube uses lazy loading)
            self._scroll_page_to_load_content(self.page, scroll_count=5)

            # Extract video IDs from href attributes
            # YouTube video links follow pattern: /watch?v=VIDEO_ID
            video_links = self.page.query_selector_all("a#video-title")

            logger.info(f"Found {len(video_links)} video links on page")

            for link in video_links[:max_videos]:
                href = link.get_attribute("href")
                if href:
                    # Extract video ID from URL
                    video_id = self._extract_video_id_from_url(href)
                    if video_id and video_id not in video_ids:
                        video_ids.append(video_id)

        except Exception as e:
            logger.error(f"Error extracting video IDs: {str(e)}")
            raise

        return video_ids

    def _scroll_page_to_load_content(self, page: Page, scroll_count: int = 5):
        """
        Scroll the page to trigger lazy loading of more videos.

        Args:
            page: Playwright page object
            scroll_count: Number of times to scroll down
        """
        for i in range(scroll_count):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)  # Wait 1 second between scrolls
            logger.debug(f"Scroll {i+1}/{scroll_count} completed")

    def _extract_video_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from a URL.

        Args:
            url: YouTube URL (e.g., "/watch?v=VIDEO_ID" or full URL)

        Returns:
            Video ID string or None if not found
        """
        # Match patterns like: /watch?v=VIDEO_ID or ?v=VIDEO_ID
        patterns = [
            r"[?&]v=([a-zA-Z0-9_-]{11})",  # Standard YouTube video ID
            r"/watch/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _transcript_exists(self, youtube_id: str) -> bool:
        """
        Check if a transcript already exists in the database.

        Args:
            youtube_id: YouTube video ID to check

        Returns:
            True if transcript exists, False otherwise
        """
        if not self.database:
            logger.warning("No database connection available")
            return False

        return self.database.transcript_exists_by_youtube_id(youtube_id)

    def _add_to_queue(self, youtube_id: str, source_url: str) -> bool:
        """
        Add a YouTube video ID to the transcript queue.

        Args:
            youtube_id: YouTube video ID to queue
            source_url: Source URL where the video was discovered

        Returns:
            True if successfully added, False otherwise
        """
        if not self.database:
            logger.error("Cannot add to queue - no database connection")
            return False

        try:
            self.database.cursor.execute(
                """INSERT OR IGNORE INTO transcript_queue 
                   (youtube_id, source_url, discovered_at, status) 
                   VALUES (?, ?, ?, ?)""",
                (youtube_id, source_url, datetime.now().isoformat(), "pending"),
            )
            self.database.conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to add {youtube_id} to queue: {str(e)}")
            return False

    def get_queue_stats(self) -> Dict[str, int]:
        """
        Get statistics about the current transcript queue.

        Returns:
            Dict with queue statistics
        """
        if not self.database:
            return {"error": "No database connection"}

        try:
            cursor = self.database.cursor

            # Total pending
            cursor.execute(
                "SELECT COUNT(*) FROM transcript_queue WHERE status = 'pending'"
            )
            pending = cursor.fetchone()[0]

            # Total processing
            cursor.execute(
                "SELECT COUNT(*) FROM transcript_queue WHERE status = 'processing'"
            )
            processing = cursor.fetchone()[0]

            # Total failed
            cursor.execute(
                "SELECT COUNT(*) FROM transcript_queue WHERE status = 'failed'"
            )
            failed = cursor.fetchone()[0]

            return {
                "pending": pending,
                "processing": processing,
                "failed": failed,
                "total": pending + processing + failed,
            }

        except Exception as e:
            logger.error(f"Failed to get queue stats: {str(e)}")
            return {"error": str(e)}

    def close(self):
        """
        Close the browser and playwright instance.
        Should be called when done using the scraper.
        """
        self.browser.close()
        self.playwright.stop()
        logger.info("Scraper browser closed")
