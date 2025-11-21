import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser
import re
from .create_database import Database

logger = logging.getLogger(__name__)


class VideoQueueManager:
    """
    Manages the video processing queue by discovering new YouTube videos and tracking them.

    This class:
    1. Queries existing transcripts to avoid duplicates
    2. Scrapes YouTube channels to discover video IDs
    3. Compares and adds only new videos to the queue

    Uses Playwright for web scraping and SQLite for queue management.
    """

    def __init__(self, database: Database):
        """
        Initialize the queue manager with a database connection.

        Args:
            database: Database instance for managing transcripts and queue (required)
        """
        self.database = database
        self.playwright = sync_playwright().start()
        self.browser: Browser = self.playwright.chromium.launch(headless=True)
        self.page: Page = self.browser.new_page()

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

    def scrape_youtube_ids(self, channel_url: str, max_limit: int = 100) -> List[str]:
        """
        Crawl YouTube channel page and extract all available video IDs up to max limit.

        Args:
            channel_url: URL of the YouTube channel/playlist/archive page
            max_limit: Maximum number of video IDs to extract (default: 100)

        Returns:
            List of YouTube video IDs discovered on the page
        """
        logger.info(f"Scraping YouTube IDs from: {channel_url} (max: {max_limit})")

        video_ids = []

        try:
            logger.info(f"Loading page: {channel_url}")
            self.page.goto(channel_url, wait_until="networkidle", timeout=30000)

            # Wait for video thumbnails to load
            self.page.wait_for_selector("a#video-title", timeout=10000)

            # Scroll to load more videos (YouTube uses lazy loading)
            self._scroll_page_to_load_content(self.page, scroll_count=5)

            # Extract video IDs from href attributes
            # YouTube video links follow pattern: /watch?v=VIDEO_ID
            video_links = self.page.query_selector_all("a#video-title")

            logger.info(f"Found {len(video_links)} video links on page")

            for link in video_links[:max_limit]:
                href = link.get_attribute("href")
                if href:
                    # Extract video ID from URL
                    video_id = self._extract_video_id_from_url(href)
                    if video_id and video_id not in video_ids:
                        video_ids.append(video_id)

            logger.info(f"Extracted {len(video_ids)} unique video IDs")
            return video_ids

        except Exception as e:
            logger.error(f"Error extracting video IDs: {str(e)}")
            raise

    def queue_new_videos(
        self, channel_url: str, max_limit: int = 100
    ) -> Dict[str, Any]:
        """
        Compare scraped IDs with existing transcripts and add new ones to the queue.

        This method:
        1. Gets all existing youtube_ids from transcripts table
        2. Scrapes the YouTube channel for video IDs
        3. Compares the two lists
        4. Adds only new (non-existing) IDs to the video_queue

        Args:
            channel_url: URL of the YouTube channel to scrape
            max_limit: Maximum number of videos to process (default: 100)

        Returns:
            Dict containing results:
                - total_discovered: Number of videos found on YouTube
                - already_exists: Number of videos that already have transcripts
                - newly_queued: Number of videos added to queue
                - skipped: Number of videos skipped (already exist)
                - youtube_ids: List of all discovered IDs
        """
        logger.info(f"Starting queue_new_videos for: {channel_url}")

        results = {
            "total_discovered": 0,
            "already_exists": 0,
            "newly_queued": 0,
            "skipped": 0,
            "failed": 0,
            "youtube_ids": [],
        }

        try:
            # Step 1: Get existing youtube_ids from database
            existing_ids = self.get_existing_youtube_ids()
            logger.info(f"Found {len(existing_ids)} existing transcripts")

            # Step 2: Scrape YouTube channel for video IDs
            scraped_ids = self.scrape_youtube_ids(channel_url, max_limit)
            results["total_discovered"] = len(scraped_ids)
            results["youtube_ids"] = scraped_ids

            logger.info(f"Discovered {len(scraped_ids)} videos on YouTube")

            # Step 3: Compare and add new videos to queue
            for youtube_id in scraped_ids:
                try:
                    # If video ID exists in transcripts, skip it
                    if youtube_id in existing_ids:
                        logger.debug(
                            f"Skipping {youtube_id} - transcript already exists"
                        )
                        results["already_exists"] += 1
                        results["skipped"] += 1
                    else:
                        # Add to queue if it doesn't exist
                        if self._add_to_queue(youtube_id):
                            logger.info(f"Added {youtube_id} to video queue")
                            results["newly_queued"] += 1
                        else:
                            logger.warning(f"Failed to queue {youtube_id}")
                            results["failed"] += 1

                except Exception as e:
                    logger.error(f"Error processing video ID {youtube_id}: {str(e)}")
                    results["failed"] += 1

            logger.info(
                f"Queue processing complete: {results['total_discovered']} discovered, "
                f"{results['already_exists']} already exist, {results['newly_queued']} newly queued, "
                f"{results['skipped']} skipped, {results['failed']} failed"
            )

            return results

        except Exception as e:
            logger.error(f"Failed to queue new videos: {str(e)}")
            raise

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

    def _add_to_queue(self, youtube_id: str) -> bool:
        """
        Add a YouTube video ID to the video_queue table.

        Args:
            youtube_id: YouTube video ID to queue

        Returns:
            True if successfully added, False otherwise
        """
        if not self.database:
            logger.error("Cannot add to queue - no database connection")
            return False

        try:
            self.database.cursor.execute(
                """INSERT OR IGNORE INTO video_queue 
                   (youtube_id, transcript_available) 
                   VALUES (?, ?)""",
                (youtube_id, 0),  # transcript_available defaults to 0 (false)
            )
            self.database.conn.commit()
            return True

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

            # With errors
            cursor.execute(
                "SELECT COUNT(*) FROM video_queue WHERE error_message IS NOT NULL"
            )
            errors = cursor.fetchone()[0]

            return {
                "total": total,
                "transcript_available": available,
                "pending": pending,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Failed to get queue stats: {str(e)}")
            return {"error": str(e)}

    def close(self):
        """
        Close the browser and playwright instance.
        Should be called when done using the queue manager.
        """
        self.browser.close()
        self.playwright.stop()
        logger.info("VideoQueueManager browser closed")
