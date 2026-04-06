"""
Pipeline service orchestrating the full content production workflow.

The pipeline runs in stages, each handled by a dedicated method on
``PipelineService``:

1. **Build queue** (``run_build_queue``) — Scrape a YouTube channel and
   populate ``video_queue`` with new video IDs that haven't been
   processed yet.

2. **Fetch transcripts** (``run_bulk_fetch_transcripts``) — Pull
   transcripts for queued videos, either from YouTube's built-in captions
   or via OpenAI Whisper when captions are unavailable, and persist them
   to ``transcripts``.

3. **Write articles** (``run_bulk_write_articles``) — Feed transcripts to
   an AI journalist (e.g. AureliusStone or FRJ1) to produce structured
   articles, which are saved to ``articles``.

4. **Bullet points** (``run_bullet_points_batch``) — Generate short
   bullet-point summaries for articles that don't have them yet.

5. **Image generation** (``run_image_batch``) — Create an AI-generated
   cover image for each article that has bullet points but no art, saving
   results to the ``art`` table.

All methods return plain ``dict`` result objects so they can be serialised
directly to JSON by the pipeline router.
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
    Orchestrates each stage of the content production pipeline.

    The service is intentionally dependency-injected: each collaborator
    (database, transcript manager, etc.) is passed in at construction
    time so individual stages can degrade gracefully when a dependency is
    unavailable (they return a ``success: False`` dict rather than
    raising).

    Typical call order for a full pipeline run::

        svc = PipelineService(db, transcript_mgr, journalist_mgr, image_svc)

        await svc.run_build_queue(channel_url, limit=10)
        await svc.run_bulk_fetch_transcripts(amount=10, auto_build=False)
        await svc.run_bulk_write_articles(amount=10, journalist=..., tone=..., article_type=...)
        svc.run_bullet_points_batch(amount=10)
        svc.run_image_batch(amount=10, artist=..., model=...)
    """

    def __init__(
        self,
        database: Optional[Database],
        transcript_manager: Optional[TranscriptManager],
        journalist_manager: Optional[JournalistManager],
        image_service: Optional[ImageService],
    ) -> None:
        """
        Args:
            database: SQLite database wrapper used by all pipeline stages.
            transcript_manager: Handles YouTube caption fetching and Whisper
                transcription.
            journalist_manager: Persists and retrieves journalist profile
                records used when saving articles.
            image_service: Utility for downloading/decoding remote image URLs
                before storing them in the database.
        """
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
        """Scrape a YouTube channel and add new videos to ``video_queue``.

        Delegates to ``VideoQueueManager.queue_new_videos``, which walks the
        channel's upload history until it has found ``limit`` videos that are
        not yet in the queue or the transcripts table.

        Args:
            channel_url: Full YouTube channel URL (e.g.
                ``https://www.youtube.com/@SomeChannel``).
            limit: Maximum number of new videos to add to the queue.
            skip_youtube_ids_on_wp: YouTube IDs that are already published on
                WordPress and should therefore never be queued.

        Returns:
            A dict with keys:

            - ``success`` (bool): ``False`` only when the database is
              unavailable.
            - ``message`` (str): Human-readable summary.
            - ``results`` (dict): Raw output from
              ``VideoQueueManager.queue_new_videos``, including a
              ``newly_queued`` count.
        """
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
        """Fetch transcripts for queued videos and persist them to ``transcripts``.

        Works through ``video_queue`` in priority order: videos that need
        Whisper (``transcript_available=0``) are attempted first because they
        are slower; caption-only videos follow.  A 5-second rate-limit delay
        is applied between each attempt to avoid hammering the YouTube API or
        Whisper service.

        **Failure handling**: if a video fails to transcribe (including after
        the Whisper fallback), it is logged at ERROR level, skipped for this
        run, and left in the queue for the next run.  The loop continues with
        the next queued video.  Only when zero transcripts are successfully
        fetched across all attempts does the method return ``success: False``,
        which stops all downstream pipeline steps.

        **Auto-build**: when the queue has fewer pending items than
        ``amount``, and ``auto_build=True``, the method calls
        ``run_build_queue`` internally to top up the queue before processing.

        Args:
            amount: Target number of *successful* transcript fetches.
            auto_build: When ``True`` and the queue is too short, auto-
                matically scrape the channel for more videos before fetching.
            channel_url: Channel to scrape during auto-build.  Falls back to
                the ``DEFAULT_YOUTUBE_CHANNEL_URL`` environment variable.
            skip_youtube_ids_on_wp: IDs already on WordPress; any matching
                queue entries are silently removed rather than fetched.
            include_whisper_items: When ``False``, only videos that have
                native YouTube captions (``transcript_available=1``) are
                processed.  Useful when Whisper quota is exhausted.

        Returns:
            A dict with keys:

            - ``success`` (bool): ``False`` when a dependency is unavailable,
              the queue was empty, or any transcript fetch fails.
            - ``message`` (str): Human-readable summary of attempts vs.
              successes.
            - ``transcripts_fetched`` (int)
            - ``transcripts_failed`` (int)
            - ``results`` (list[dict]): Per-video status with ``youtube_id``,
              ``status`` (``"success"`` / ``"failed"``), ``source``,
              ``from_cache``, and ``saved_to_db`` fields.
            - ``auto_build`` (dict, optional): Present only when an auto-
              build was triggered; includes ``videos_added`` and
              ``channel_url``.
        """
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
        results = []
        transcripts_fetched = 0
        transcripts_failed = 0
        attempts = 0
        RATE_LIMIT_MS = 5000
        # Track IDs that failed this run so we skip them in subsequent iterations
        # without removing them from the queue (they stay for the next run).
        failed_this_run: Set[str] = set()

        def _pop_next_queue_row():
            exclude_clause = ""
            exclude_params: tuple = ()
            if failed_this_run:
                placeholders = ",".join(["?"] * len(failed_this_run))
                exclude_clause = f" AND T1.youtube_id NOT IN ({placeholders})"
                exclude_params = tuple(failed_this_run)
            cursor.execute(
                """SELECT T1.youtube_id, T1.transcript_available
                   FROM video_queue AS T1
                   LEFT JOIN transcripts AS T2 ON T1.youtube_id = T2.youtube_id
                   WHERE T2.youtube_id IS NULL"""
                + caption_only_clause
                + exclude_clause
                + """
                   ORDER BY T1.id ASC
                   LIMIT 1""",
                exclude_params,
            )
            return cursor.fetchone()

        while transcripts_fetched < amount:
            row = _pop_next_queue_row()
            if not row:
                break
            youtube_id = row[0]
            transcript_available = row[1] if len(row) > 1 else 1
            yid = (youtube_id or "").strip()
            if not yid:
                cursor.execute("DELETE FROM video_queue WHERE youtube_id = ?", (youtube_id,))
                db.conn.commit()
                continue
            if yid in on_wp:
                cursor.execute("DELETE FROM video_queue WHERE youtube_id = ?", (yid,))
                db.conn.commit()
                logger.info("Skipping %s - already on WordPress (removed from queue)", yid)
                continue
            attempts += 1
            try:
                transcript_result = transcript_mgr.get_transcript(
                    youtube_id, allow_whisper_fallback=include_whisper_items
                )
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
                text_len = len(
                    transcript_result.get("transcript")
                    or transcript_result.get("content")
                    or ""
                )
                logger.info(
                    "Transcript fetch OK: youtube_id=%s source=%s from_cache=%s chars=%s",
                    youtube_id,
                    transcript_result.get("source"),
                    from_cache,
                    text_len,
                )
                cursor.execute(
                    "DELETE FROM video_queue WHERE youtube_id = ?", (youtube_id,)
                )
                db.conn.commit()
            except Exception as e:
                transcripts_failed += 1
                failed_this_run.add(yid)
                results.append({
                    "youtube_id": youtube_id,
                    "status": "failed",
                    "error": str(e),
                })
                # Mark as transcript_available=0 so SKIP_WHISPER mode ignores it next run.
                # It stays in the queue and will be retried when USE_WHISPER mode is active.
                cursor.execute(
                    "UPDATE video_queue SET transcript_available = 0 WHERE youtube_id = ?",
                    (yid,),
                )
                db.conn.commit()
                logger.warning(
                    "Transcript fetch failed for youtube_id=%s; marked transcript_available=0 in queue: %s",
                    youtube_id,
                    e,
                )
            time.sleep(RATE_LIMIT_MS / 1000.0)

        if transcripts_fetched == 0:
            message = (
                "No videos in queue without a transcript"
                if attempts == 0
                else f"All {attempts} transcript fetch attempt(s) failed; no transcripts fetched this run"
            )
            return {
                "success": False,
                "message": message,
                "transcripts_fetched": 0,
                "transcripts_failed": transcripts_failed,
                "results": results,
            }
        message = (
            f"Processed {attempts} attempt(s); fetched {transcripts_fetched} (requested up to {amount})"
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
        """Generate articles from stored transcripts using an AI journalist.

        Selects up to ``amount`` transcripts that do not yet have a
        corresponding article (``LEFT JOIN articles … WHERE a.id IS NULL``),
        oldest first.  For each transcript the journalist's ``load_context``
        and ``generate_article`` methods are called, and the resulting article
        is saved via ``Database.add_article``.

        If the journalist profile doesn't exist in the database yet it is
        created automatically via ``JournalistManager.upsert_journalist``.

        When no eligible transcripts are found, the method returns a detailed
        diagnostics block explaining how many transcripts exist without
        articles and how many were excluded due to the WordPress skip-list,
        which helps distinguish "nothing to do" from "everything is already
        published".

        Args:
            amount: Maximum number of articles to generate in this call.
            journalist: Which AI journalist persona to use (see
                ``Journalist`` enum).
            tone: Writing tone to pass to the journalist's context loader
                (e.g. ``Tone.NEUTRAL``, ``Tone.EDITORIAL``).
            article_type: Article format/type (e.g. ``ArticleType.STANDARD``).
            skip_youtube_ids: YouTube IDs whose transcripts should be ignored
                because the corresponding article already exists on WordPress.

        Returns:
            A dict with keys:

            - ``success`` (bool): ``False`` when dependencies are missing or
              no eligible transcripts were found.
            - ``message`` (str): Human-readable summary.
            - ``articles_generated`` (int)
            - ``articles_failed`` (int)
            - ``article_ids`` (list[int]): Database IDs of newly created
              articles.
            - ``results`` (list[dict]): Per-transcript status with
              ``youtube_id``, ``transcript_id``, ``status``, and ``title``.
            - ``diagnostics`` (dict, optional): Present only when 0
              transcripts were eligible; contains ``transcripts_without_
              article``, ``excluded_by_wordpress``, and
              ``skip_youtube_ids_count``.

        Raises:
            ValueError: If the ``journalist`` enum value has no corresponding
                implementation class, or the journalist profile could not be
                created in the database.
        """
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
                logger.warning("Pipeline article write failed for youtube_id=%s: %s", youtube_id, e)
        return {
            "success": True,
            "message": f"Processed {len(transcripts)} transcripts",
            "articles_generated": articles_generated,
            "articles_failed": articles_failed,
            "article_ids": article_ids,
            "results": results,
        }

    def run_bullet_points_batch(self, amount: int) -> Dict[str, Any]:
        """Generate bullet-point summaries for articles that don't have them yet.

        Retrieves all articles, filters to those without ``bullet_points``,
        then processes the newest ones first (descending ``id`` order).  This
        ordering ensures that articles produced earlier in the same pipeline
        run receive their summaries before older, potentially stale rows.

        Bullet-point generation is handled by ``AureliusStone`` regardless of
        which journalist originally wrote the article, since the summarisation
        prompt is journalist-agnostic.

        Errors on individual articles are collected in the ``errors`` list and
        do not abort the batch.

        Args:
            amount: Maximum number of articles to process in this call.

        Returns:
            A dict with keys:

            - ``processed`` (int): Number of articles successfully given
              bullet points.
            - ``skipped`` (int): Number of articles that already had bullet
              points and were not re-processed.
            - ``errors`` (list[dict]): Any per-article failures, each with
              ``id`` and ``error`` keys.
        """
        db = self._database
        if not db:
            return {"processed": 0, "skipped": 0, "errors": []}
        all_articles = db.get_all_articles()
        articles = [a for a in all_articles if not a.get("bullet_points")]
        articles.sort(key=lambda a: a["id"], reverse=True)
        journalist = AureliusStone()
        results = {
            "processed": 0,
            "skipped": len(all_articles) - len(articles),
            "errors": [],
        }
        for article in articles:
            if results["processed"] >= amount:
                break
            try:
                result = journalist.generate_bullet_points(article["content"])
            except Exception as e:
                results["errors"].append({"id": article["id"], "error": str(e)})
                logger.warning("Pipeline bullet points failed for article id=%s: %s", article["id"], e)
                continue
            if result.get("error"):
                results["errors"].append({"id": article["id"], "error": result["error"]})
                logger.warning("Pipeline bullet points error for article id=%s: %s", article["id"], result["error"])
                continue
            db.update_article_bullet_points(article["id"], result["bullet_points"])
            results["processed"] += 1
        return results

    def run_image_batch(
        self, amount: int, artist: Artist, model: ImageModel
    ) -> Dict[str, Any]:
        """Generate AI cover images for articles that have bullet points but no art.

        Queries for articles where ``bullet_points`` is populated and no row
        exists yet in the ``art`` table (``LEFT JOIN art … WHERE art.id IS
        NULL``), newest first, up to ``amount``.

        For each article the artist's ``generate_image`` method is called with
        the article title and bullet points.  If the artist returns an
        ``image_url``, the raw image bytes are fetched via
        ``ImageService.decode_url`` and stored in the ``art`` table alongside
        the prompt, medium, aesthetic, and other metadata.

        A second existence check is performed inside the loop (before calling
        the model) to guard against race conditions where art was added
        between the initial query and the current iteration.

        Args:
            amount: Maximum number of images to generate.
            artist: Which AI artist persona to use (see ``Artist`` enum).
            model: Image model to use for generation (see ``ImageModel`` enum);
                the enum value is passed directly to the artist and stored in
                the database for provenance.

        Returns:
            A dict with keys:

            - ``success`` (bool): Always ``True`` (individual failures are
              captured in ``results``); ``False`` only when a required
              dependency is unavailable.
            - ``message`` (str): Human-readable summary.
            - ``images_generated`` (int)
            - ``images_failed`` (int)
            - ``results`` (list[dict]): Per-article status with
              ``article_id``, ``status`` (``"success"`` / ``"failed"`` /
              ``"skipped"``), and either ``art_id`` + ``title`` on success or
              an ``error`` string on failure.

        Raises:
            ValueError: If the ``artist`` enum value has no corresponding
                implementation class.
        """
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
               ORDER BY a.id DESC
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
                logger.warning("Pipeline image generate failed for article_id=%s: %s", article_id, e)
        return {
            "success": True,
            "message": f"Processed {len(articles)} articles",
            "images_generated": images_generated,
            "images_failed": images_failed,
            "results": results,
        }
