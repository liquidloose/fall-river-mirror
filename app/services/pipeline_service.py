"""
Pipeline service: build queue, bulk fetch transcripts, bulk write articles,
bullet points batch, image batch. Used by the pipeline router.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi.responses import JSONResponse

from app import TranscriptManager
from app.content_department.ai_artists.fra1 import FRA1
from app.content_department.ai_artists.spectra_veritas import SpectraVeritas
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_journalists.fr_j1 import FRJ1
from app.data.create_database import Database
from app.data.enum_classes import ArticleType, Artist, ImageModel, Journalist, Tone
from app.data.journalist_manager import JournalistManager
from app.data.video_queue_manager import VideoQueueManager
from app.services.image_service import ImageService

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Runs pipeline steps: queue build, transcript fetch, article write,
    bullet points, image generation. Each method returns a result dict.
    """

    def __init__(
        self,
        database: Optional[Database],
        transcript_manager: Optional[TranscriptManager],
        journalist_manager: Optional[JournalistManager],
        image_service: Optional[ImageService],
    ) -> None:
        self._database = database
        self._transcript_manager = transcript_manager
        self._journalist_manager = journalist_manager
        self._image_service = image_service

    async def run_build_queue(
        self,
        channel_url: str,
        limit: int,
        skip_youtube_ids_on_wp: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Build video queue; returns result dict. skip_youtube_ids_on_wp: do not queue these (already on WordPress)."""
        db = self._database
        if not db:
            return {"success": False, "error": "Database not available", "results": []}
        async with VideoQueueManager(db) as queue_manager:
            results = await queue_manager.queue_new_videos(
                channel_url,
                target_new_videos=limit,
                skip_youtube_ids_on_wp=skip_youtube_ids_on_wp or set(),
            )
        return {
            "success": True,
            "message": f"Queue built successfully from {channel_url}",
            "results": results,
        }

    async def run_bulk_fetch_transcripts(
        self,
        amount: int,
        auto_build: bool,
        channel_url: Optional[str] = None,
        skip_youtube_ids_on_wp: Optional[Set[str]] = None,
        include_whisper_items: bool = True,
    ) -> Dict[str, Any]:
        """Bulk fetch transcripts from queue; returns result dict.
        skip_youtube_ids_on_wp: do not fetch these (already on WordPress).
        include_whisper_items: if False, only select videos with captions (transcript_available=1); skip Whisper-needed items."""
        db = self._database
        transcript_mgr = self._transcript_manager
        if not db or not transcript_mgr:
            return {
                "success": False,
                "message": "Database or transcript manager not available",
                "transcripts_fetched": 0,
                "transcripts_failed": 0,
                "results": [],
            }
        on_wp = skip_youtube_ids_on_wp or set()
        channel_url = channel_url or os.getenv("DEFAULT_YOUTUBE_CHANNEL_URL")
        cursor = db.cursor
        # Restrict to caption-available only when Skip Whisper mode
        caption_only_clause = "" if include_whisper_items else " AND T1.transcript_available = 1"
        cursor.execute(
            """SELECT COUNT(*)
               FROM video_queue AS T1
               LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
               WHERE T2.youtube_id IS NULL"""
            + caption_only_clause
        )
        available_count = cursor.fetchone()[0]
        auto_build_triggered = False
        auto_build_added = 0
        if available_count < amount and auto_build and channel_url:
            auto_build_triggered = True
            shortfall = amount - available_count
            try:
                async with VideoQueueManager(db) as queue_manager:
                    build_results = await queue_manager.queue_new_videos(
                        channel_url,
                        target_new_videos=shortfall,
                        skip_youtube_ids_on_wp=on_wp,
                    )
                auto_build_added = build_results.get("newly_queued", 0)
            except Exception as e:
                logger.warning(f"Auto-build queue failed: {e}. Proceeding with available.")
        # When include_whisper_items: process Whisper-needed first, then oldest. Otherwise only caption-available (oldest first).
        cursor.execute(
            """SELECT T1.youtube_id, T1.transcript_available
               FROM video_queue AS T1
               LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
               WHERE T2.youtube_id IS NULL"""
            + caption_only_clause
            + """
               ORDER BY T1.transcript_available ASC, T1.id ASC
               LIMIT ?""",
            (amount,),
        )
        raw_queue_items = cursor.fetchall()
        # Skip videos already on WordPress: remove from queue and do not fetch transcript
        queue_items = []
        for row in raw_queue_items:
            yid = (row[0] or "").strip()
            if yid and yid in on_wp:
                cursor.execute("DELETE FROM video_queue WHERE youtube_id = ?", (yid,))
                db.conn.commit()
                logger.info("Skipping %s - already on WordPress (removed from queue)", yid)
                continue
            queue_items.append(row)
        if not queue_items:
            return {
                "success": False,
                "message": "No videos in queue without a transcript",
                "transcripts_fetched": 0,
                "transcripts_failed": 0,
                "results": [],
            }
        results = []
        transcripts_fetched = 0
        transcripts_failed = 0
        RATE_LIMIT_MS = 5000
        for row in queue_items:
            youtube_id = row[0]
            transcript_available = row[1] if len(row) > 1 else 1
            try:
                if transcript_available == 0:
                    logger.info("Queue item %s has no captions; using Whisper", youtube_id)
                    transcript_result = transcript_mgr.get_transcript_via_whisper(youtube_id)
                else:
                    transcript_result = transcript_mgr.get_transcript(youtube_id)
                if isinstance(transcript_result, JSONResponse):
                    error_content = json.loads(transcript_result.body.decode())
                    raise Exception(
                        error_content.get("error", "Unknown error during transcript fetch")
                    )
                transcripts_fetched += 1
                from_cache = transcript_result.get("source") == "database_cache"
                # Verify new transcripts are actually in DB so we don't report success without persist
                if not from_cache:
                    cursor.execute(
                        "SELECT id FROM transcripts WHERE youtube_id = ?", (youtube_id,)
                    )
                    if not cursor.fetchone():
                        raise Exception(
                            "Transcript was not saved to database (verify failed after cache)"
                        )
                results.append({
                    "youtube_id": youtube_id,
                    "status": "success",
                    "source": transcript_result.get("source"),
                    "from_cache": from_cache,
                    "saved_to_db": from_cache or True,
                })
                cursor.execute(
                    "DELETE FROM video_queue WHERE youtube_id = ?", (youtube_id,)
                )
                db.conn.commit()
            except Exception as e:
                transcripts_failed += 1
                results.append({"youtube_id": youtube_id, "status": "failed", "error": str(e)})
            time.sleep(RATE_LIMIT_MS / 1000.0)
        message = (
            f"Processed {len(queue_items)} videos from queue"
            if len(queue_items) >= amount
            else f"Processed {len(queue_items)} videos from queue (requested {amount}, only {len(queue_items)} available)"
        )
        response = {
            "success": True,
            "message": message,
            "transcripts_fetched": transcripts_fetched,
            "transcripts_failed": transcripts_failed,
            "results": results,
        }
        if auto_build_triggered:
            response["auto_build"] = {
                "triggered": True,
                "videos_added": auto_build_added,
                "channel_url": channel_url,
            }
        return response

    async def run_bulk_write_articles(
        self,
        amount: int,
        journalist: Journalist,
        tone: Tone,
        article_type: ArticleType,
        skip_youtube_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Bulk write articles from transcripts; returns result dict. skip_youtube_ids: do not write articles for these (e.g. already on WordPress)."""
        db = self._database
        journalist_mgr = self._journalist_manager
        if not db or not journalist_mgr:
            return {
                "success": False,
                "message": "Database or journalist manager not available",
                "articles_generated": 0,
                "articles_failed": 0,
                "article_ids": [],
                "results": [],
            }
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
            Journalist.FR_J1: FRJ1,
        }
        journalist_class = journalist_classes.get(journalist)
        if not journalist_class:
            raise ValueError(f"Journalist '{journalist.value}' not implemented")
        journalist_instance = journalist_class()
        journalist_data = journalist_mgr.get_journalist(journalist_instance.FULL_NAME)
        if not journalist_data:
            journalist_mgr.upsert_journalist(
                full_name=journalist_instance.FULL_NAME,
                first_name=journalist_instance.FIRST_NAME,
                last_name=journalist_instance.LAST_NAME,
                bio=journalist_instance.get_bio(),
                description=journalist_instance.get_description(),
            )
            journalist_data = journalist_mgr.get_journalist(journalist_instance.FULL_NAME)
        if not journalist_data:
            raise ValueError(
                f"Failed to create or retrieve journalist {journalist_instance.FULL_NAME}"
            )
        journalist_id = journalist_data["id"]
        cursor = db.cursor
        if skip_youtube_ids:
            placeholders = ",".join(["?"] * len(skip_youtube_ids))
            cursor.execute(
                f"""SELECT t.id, t.committee, t.youtube_id, t.content
                   FROM transcripts t
                   LEFT JOIN articles a ON t.id = a.transcript_id
                   WHERE a.id IS NULL AND (t.youtube_id IS NULL OR t.youtube_id NOT IN ({placeholders}))
                   ORDER BY t.id ASC
                   LIMIT ?""",
                (*skip_youtube_ids, amount),
            )
        else:
            cursor.execute(
                """SELECT t.id, t.committee, t.youtube_id, t.content
                   FROM transcripts t
                   LEFT JOIN articles a ON t.id = a.transcript_id
                   WHERE a.id IS NULL
                   ORDER BY t.id ASC
                   LIMIT ?""",
                (amount,),
            )
        transcripts = cursor.fetchall()
        if not transcripts:
            # Diagnose why 0: count transcripts without articles, and how many excluded by WordPress
            cursor.execute(
                """SELECT COUNT(*) FROM transcripts t
                   LEFT JOIN articles a ON t.id = a.transcript_id WHERE a.id IS NULL"""
            )
            without_article = cursor.fetchone()[0]
            excluded_by_wp = 0
            if skip_youtube_ids:
                cursor.execute(
                    """SELECT COUNT(*) FROM transcripts t
                       LEFT JOIN articles a ON t.id = a.transcript_id
                       WHERE a.id IS NULL AND t.youtube_id IS NOT NULL AND t.youtube_id IN ("""
                    + ",".join(["?"] * len(skip_youtube_ids)) + ")",
                    tuple(skip_youtube_ids),
                )
                excluded_by_wp = cursor.fetchone()[0]
            excluded_msg = f"; {excluded_by_wp} excluded (already on WordPress)" if excluded_by_wp else ""
            message = (
                f"No transcripts eligible for article write: {without_article} without articles{excluded_msg}"
                if without_article or excluded_by_wp else "No transcripts found in database"
            )
            return {
                "success": False,
                "message": message,
                "articles_generated": 0,
                "articles_failed": 0,
                "article_ids": [],
                "results": [],
                "diagnostics": {
                    "transcripts_without_article": without_article,
                    "excluded_by_wordpress": excluded_by_wp,
                    "skip_youtube_ids_count": len(skip_youtube_ids) if skip_youtube_ids else 0,
                },
            }
        results = []
        article_ids = []
        articles_generated = 0
        articles_failed = 0
        for row in transcripts:
            transcript_id, committee, youtube_id, transcript_content = (
                row[0], row[1], row[2], row[3],
            )
            try:
                base_context = journalist_instance.load_context(
                    tone=tone, article_type=article_type
                )
                full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
                article_result = journalist_instance.generate_article(full_context, "")
                new_id = db.add_article(
                    committee=committee,
                    youtube_id=youtube_id,
                    journalist_id=journalist_id,
                    content=article_result["content"],
                    transcript_id=transcript_id,
                    date=datetime.now().isoformat(),
                    article_type=article_type.value,
                    tone=tone.value,
                    title=article_result.get("title", "Untitled Article"),
                )
                articles_generated += 1
                article_ids.append(new_id)
                results.append({
                    "youtube_id": youtube_id,
                    "transcript_id": transcript_id,
                    "status": "success",
                    "title": article_result.get("title", "Untitled Article"),
                })
            except Exception as e:
                articles_failed += 1
                results.append({"youtube_id": youtube_id, "status": "failed", "error": str(e)})
        return {
            "success": True,
            "message": f"Processed {len(transcripts)} transcripts",
            "articles_generated": articles_generated,
            "articles_failed": articles_failed,
            "article_ids": article_ids,
            "results": results,
        }

    def run_bullet_points_batch(self, amount: int) -> Dict[str, Any]:
        """Generate bullet points for articles that don't have them; returns result dict."""
        db = self._database
        if not db:
            return {"processed": 0, "skipped": 0, "errors": []}
        articles = db.get_all_articles()
        journalist = AureliusStone()
        results = {"processed": 0, "skipped": 0, "errors": []}
        for article in articles:
            if results["processed"] >= amount:
                break
            if article.get("bullet_points"):
                results["skipped"] += 1
                continue
            result = journalist.generate_bullet_points(article["content"])
            if result.get("error"):
                results["errors"].append({"id": article["id"], "error": result["error"]})
                continue
            db.update_article_bullet_points(article["id"], result["bullet_points"])
            results["processed"] += 1
        return results

    def run_image_batch(
        self, amount: int, artist: Artist, model: ImageModel
    ) -> Dict[str, Any]:
        """Generate images for articles with bullet_points but no art; returns result dict."""
        db = self._database
        image_svc = self._image_service
        if not db or not image_svc:
            return {
                "success": True,
                "message": "Database or image service not available",
                "images_generated": 0,
                "images_failed": 0,
                "results": [],
            }
        artist_classes = {
            Artist.SPECTRA_VERITAS: SpectraVeritas,
            Artist.FRA1: FRA1,
        }
        artist_class = artist_classes.get(artist)
        if not artist_class:
            raise ValueError(f"Artist '{artist.value}' not implemented")
        artist_instance = artist_class()
        cursor = db.cursor
        cursor.execute(
            """SELECT a.id, a.title, a.bullet_points, a.transcript_id
               FROM articles a
               LEFT JOIN art ON a.id = art.article_id
               WHERE a.bullet_points IS NOT NULL AND a.bullet_points != '' AND art.id IS NULL
               LIMIT ?""",
            (amount,),
        )
        articles = cursor.fetchall()
        if not articles:
            return {
                "success": True,
                "message": "No articles found that need images",
                "images_generated": 0,
                "images_failed": 0,
                "results": [],
            }
        results = []
        images_generated = 0
        images_failed = 0
        for row in articles:
            article_id, title, bullet_points, transcript_id = row[0], row[1], row[2], row[3]
            try:
                cursor.execute("SELECT id FROM art WHERE article_id = ?", (article_id,))
                if cursor.fetchone():
                    results.append({
                        "article_id": article_id,
                        "status": "skipped",
                        "reason": "Art exists",
                    })
                    continue
                image_result = artist_instance.generate_image(
                    title=title, bullet_points=bullet_points, model=model.value
                )
                if image_result.get("error"):
                    images_failed += 1
                    results.append({
                        "article_id": article_id,
                        "status": "failed",
                        "error": image_result["error"],
                    })
                    continue
                if image_result.get("image_url"):
                    image_data = image_svc.decode_url(image_result["image_url"])
                    art_id = db.add_art(
                        prompt=image_result["prompt_used"],
                        image_url=None,
                        image_data=image_data,
                        medium=image_result.get("medium"),
                        aesthetic=image_result.get("aesthetic"),
                        title=title,
                        artist_name=image_result.get("artist"),
                        snippet=image_result.get("snippet"),
                        transcript_id=transcript_id,
                        article_id=article_id,
                        model=model.value,
                    )
                    images_generated += 1
                    results.append({
                        "article_id": article_id,
                        "status": "success",
                        "art_id": art_id,
                        "title": title,
                    })
                else:
                    images_failed += 1
                    results.append({
                        "article_id": article_id,
                        "status": "failed",
                        "error": "No image URL",
                    })
            except Exception as e:
                images_failed += 1
                results.append({"article_id": article_id, "status": "failed", "error": str(e)})
        return {
            "success": True,
            "message": f"Processed {len(articles)} articles",
            "images_generated": images_generated,
            "images_failed": images_failed,
            "results": results,
        }
