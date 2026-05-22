"""
Pipeline service: full content production workflow (queue → transcripts → articles → bullets → art).

Stages (typical order) are methods on :class:`PipelineService`:

1. **Build queue** — :meth:`run_build_queue`: scrape a YouTube channel; add new IDs to ``video_queue``.
2. **Fetch transcripts** — :meth:`run_bulk_fetch_transcripts`: captions and/or Whisper; persist to ``transcripts``.
3. **Write articles** — :meth:`run_bulk_write_articles`: AI journalist + ``transcripts`` → ``articles``.
4. **Bullet points** — :meth:`run_bullet_points_batch`: summarise bodies missing ``bullet_points``.
5. **Images** — :meth:`run_image_batch`: AI cover art for rows with bullets but no ``art`` row.

**Async vs sync**

``run_build_queue``, ``run_bulk_fetch_transcripts``, and ``run_bulk_write_articles`` are ``async``.
``run_bullet_points_batch`` and ``run_image_batch`` are synchronous.

**Return shapes (conventions)**

Returns are JSON-serializable ``dict`` objects for the pipeline router. Most stages use:

- ``success`` (``bool``) — stage-level outcome, where applicable.
- ``message`` (``str``) — short human-readable summary.
- ``results`` (``list``) — per-item status rows, where applicable.

:meth:`run_bullet_points_batch` omits top-level ``success``; it returns ``processed``,
``skipped``, and ``errors`` only. If the database is unavailable it returns
``{"processed": 0, "skipped": 0, "errors": []}``.

**Dependencies**

Constructor accepts optional :class:`~app.data.create_database.Database`,
:class:`~app.TranscriptManager`, :class:`~app.data.journalist_manager.JournalistManager`,
and :class:`~app.services.image_service.ImageService`. Missing dependencies typically
yield ``success: False`` or zero tallies; :meth:`run_image_batch` still returns
``success: True`` with an explanatory ``message`` when DB or image service is absent.
:exc:`ValueError` is raised only for unimplemented ``Journalist`` / ``Artist`` enums.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi.responses import JSONResponse

from app import TranscriptManager
from app.agent_kit.agents.artists.fra1 import FRA1
from app.agent_kit.agents.artists.spectra_veritas import SpectraVeritas
from app.agent_kit.agents.extractors.gemma_nye import GemmaNye
from app.agent_kit.agents.journalists.aurelius_stone import AureliusStone
from app.agent_kit.agents.journalists.base_journalist import ArticleGenerationError
from app.agent_kit.agents.journalists.fr_j1 import FRJ1
from app.data.anchor_manager import AnchorManager
from app.data.create_database import Database
from app.data.enum_classes import (
    ArticleType,
    Artist,
    Extractor,
    GeminiModel,
    ImageModel,
    Journalist,
    TextModel,
    Tone,
    resolve_text_model,
)
from app.data.journalist_manager import JournalistManager
from app.data.video_queue_manager import VideoQueueManager
from app.services.image_service import ImageService

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Orchestrates each stage of the content production pipeline.

    Dependencies are injected at construction time so stages can return structured
    failures (``success: False`` or empty counts) when a collaborator is missing,
    instead of raising during HTTP handling.

    **Public entry points**

    - :meth:`run_build_queue` — channel scrape → ``video_queue``
    - :meth:`run_bulk_fetch_transcripts` — ``video_queue`` → ``transcripts``
    - :meth:`run_bulk_write_articles` — ``transcripts`` → ``articles``
    - :meth:`run_bullet_points_batch` — fill ``bullet_points`` on articles
    - :meth:`run_image_batch` — ``articles`` + bullets → ``art`` rows

    **Typical full run** (pseudo-code):

    .. code-block:: python

        svc = PipelineService(db, transcript_mgr, journalist_mgr, image_svc)

        await svc.run_build_queue(channel_url, limit=10)
        await svc.run_bulk_fetch_transcripts(amount=10, auto_build=False)
        await svc.run_bulk_write_articles(
            amount=10, journalist=..., tone=..., article_type=...
        )
        svc.run_bullet_points_batch(amount=10)
        svc.run_image_batch(amount=10, artist=..., model=...)
    """

    def __init__(
        self,
        database: Optional[Database],
        transcript_manager: Optional[TranscriptManager],
        journalist_manager: Optional[JournalistManager],
        image_service: Optional[ImageService],
        anchor_manager: Optional[AnchorManager] = None,
        gemma_extractor: Optional[GemmaNye] = None,
    ) -> None:
        """
        Args:
            database: SQLite wrapper used by all pipeline stages; if ``None``,
                stages that need it return ``success: False`` or empty dicts.
            transcript_manager: YouTube captions + Whisper; required for
                :meth:`run_bulk_fetch_transcripts`.
            journalist_manager: Journalist profiles; required for
                :meth:`run_bulk_write_articles`.
            image_service: Fetches/decodes remote image bytes; required for
                :meth:`run_image_batch` to store binary art in the database.
            anchor_manager: Writes extractor output to the ``anchors`` and
                ``fact_check_removals`` tables; required for
                :meth:`run_extract_anchors`. Optional for backward compat
                with callers that only use the article/image pipeline.
            gemma_extractor: Singleton ``GemmaNye`` instance used by
                :meth:`run_extract_anchors`. Injected from ``app.state`` so
                identity/config (provider, model, prompt files) is owned at
                the app layer rather than re-instantiated per request.
                Optional for backward compat with callers that only use
                the article/image pipeline.
        """
        self._database = database
        self._transcript_manager = transcript_manager
        self._journalist_manager = journalist_manager
        self._image_service = image_service
        self._anchor_manager = anchor_manager
        self._gemma_extractor = gemma_extractor

    async def run_build_queue(
        self,
        channel_url: str,
        limit: int,
        skip_youtube_ids_on_wp: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Scrape a YouTube channel and add new videos to ``video_queue``.

        **Async** method; uses :class:`~app.data.video_queue_manager.VideoQueueManager` internally.

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
            Dict with:

            - ``success`` (``bool``): ``False`` only when the database is unavailable.
            - ``message`` (``str``): Summary for operators.
            - ``results`` (``dict``): Raw payload from
              :meth:`~app.data.video_queue_manager.VideoQueueManager.queue_new_videos`,
              including ``newly_queued`` count. On DB failure, ``results`` is ``[]``.
            - ``error`` (``str``, optional): Present when ``success`` is ``False``
              (no ``message`` on that path today — see implementation).
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

        **Async** method; performs blocking sleeps and sync DB/API work between iterations.

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
            Dict with:

            - ``success`` (``bool``): ``False`` when dependencies are missing, the
              queue had no fetchable work, **or** every attempt in this run produced
              zero new transcripts (``transcripts_fetched == 0``). If at least one
              transcript is fetched, ``success`` is ``True`` even when some videos failed.
            - ``message`` (``str``): Summary of attempts vs successes.
            - ``transcripts_fetched`` (``int``): Successful fetches this run.
            - ``transcripts_failed`` (``int``): Failed attempts this run.
            - ``results`` (``list[dict]``): Per-video rows: ``youtube_id``, ``status``
              (``"success"`` / ``"failed"``), and on success ``source``, ``from_cache``,
              ``saved_to_db``; on failure ``error``.
            - ``auto_build`` (``dict``, optional): If auto-build ran: ``triggered``,
              ``videos_added``, ``channel_url``.
            - ``error`` / ``error_code`` (optional): When Whisper is disabled and no
              caption-eligible rows exist (see implementation).

        **Stopping downstream work**

        Callers should treat ``success: False`` and ``transcripts_fetched == 0`` as
        a hard stop before article generation in the same pipeline pass.
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
            payload = {
                "success": False,
                "message": (
                    "No videos in queue without a transcript"
                    if attempts == 0
                    else f"All {attempts} transcript fetch attempt(s) failed; no transcripts fetched this run"
                ),
                "transcripts_fetched": 0,
                "transcripts_failed": transcripts_failed,
                "results": results,
            }
            if not include_whisper_items:
                payload["error"] = (
                    "Pipeline halted: no caption-available videos were eligible and Whisper fallback is disabled "
                    "(queue_mode=Skip Whisper)."
                )
                payload["error_code"] = "NO_ELIGIBLE_TRANSCRIPTS_WITH_WHISPER_DISABLED"
            return payload
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
        text_model: Optional[TextModel] = None,
    ) -> Dict[str, Any]:
        """Generate articles from stored transcripts using an AI journalist.

        **Async** method (callable with ``await`` from the pipeline); DB and LLM calls inside are synchronous.

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
            text_model: Optional unified :class:`TextModel` member selecting
                which provider + model the journalist should use to generate
                article bodies. When ``None``, the journalist's built-in
                default (xAI/Grok with the per-provider default model) is
                used, preserving prior behavior.

        Returns:
            Dict with:

            - ``success`` (``bool``): ``False`` if dependencies are missing or no
              transcript rows were eligible for this batch. If at least one row was
              processed, ``success`` is always ``True``, even when every write failed
              (check ``articles_generated`` vs ``articles_failed``).
            - ``message`` (``str``): Summary or diagnostic text.
            - ``articles_generated`` (``int``), ``articles_failed`` (``int``)
            - ``article_ids`` (``list[int]``): New ``articles.id`` values on success.
            - ``results`` (``list[dict]``): Per transcript — ``youtube_id``,
              ``transcript_id``, ``status``, ``title`` or ``error``.
            - ``diagnostics`` (``dict``, optional): When zero rows were eligible:
              ``transcripts_without_article``, ``excluded_by_wordpress``,
              ``skip_youtube_ids_count``.

        Raises:
            ValueError: Unknown ``journalist`` enum, or journalist row could not
                be created or loaded after upsert.
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
        if text_model is not None:
            llm_provider, llm_model = resolve_text_model(text_model)
            logger.info(
                "Pipeline article write: using provider=%s model=%s",
                llm_provider.value,
                llm_model.value,
            )
        else:
            llm_provider, llm_model = None, None
        for row in transcripts:
            transcript_id, committee, youtube_id, transcript_content = (
                row[0], row[1], row[2], row[3],
            )
            try:
                base_context = journalist_instance.load_context(
                    tone=tone, article_type=article_type
                )
                full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
                article_result = journalist_instance.generate_article(
                    full_context,
                    "",
                    provider=llm_provider,
                    model=llm_model,
                )
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
            except ArticleGenerationError as e:
                articles_failed += 1
                results.append({
                    "youtube_id": youtube_id,
                    "transcript_id": transcript_id,
                    "status": "failed",
                    "error": str(e),
                })
                logger.warning(
                    "Pipeline article write failed (empty or rejected xAI body) youtube_id=%s: %s",
                    youtube_id,
                    e,
                )
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
        """Generate bullet-point summaries for articles missing ``bullet_points``.

        **Sync** stage. Does not use a top-level ``success`` flag (see module conventions).

        Loads all articles via ``Database.get_all_articles``, keeps rows with empty
        ``bullet_points``, sorts by ``id`` descending (newest first so recent pipeline
        output is summarised before older rows).

        Summarisation uses :class:`~app.agent_kit.agents.journalists.aurelius_stone.AureliusStone`
        and :meth:`~app.agent_kit.agents.journalists.base_journalist.BaseJournalist.generate_bullet_points`
        regardless of which journalist authored the article.

        Per-article failures append to ``errors`` and continue the batch.

        Args:
            amount: Maximum number of articles to receive new bullet text this call.

        Returns:
            Dict with:

            - ``processed`` (``int``): Articles updated with bullet points.
            - ``skipped`` (``int``): Articles that already had ``bullet_points``.
            - ``errors`` (``list[dict]``): Failures with ``id`` and ``error`` strings.

            If ``database`` is ``None``, returns ``{"processed": 0, "skipped": 0, "errors": []}``.
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
        """Generate AI cover images for articles with bullets but no ``art`` row.

        **Sync** stage.

        Selects articles where ``bullet_points`` is non-empty and ``LEFT JOIN art`` finds
        no row, ``ORDER BY articles.id DESC``, ``LIMIT amount``. Invokes the artist's
        :meth:`~app.agent_kit.agents.artists.base_artist.BaseArtist.generate_image` with
        title, bullets, and ``model.value``. When an ``image_url`` is returned,
        :meth:`~app.services.image_service.ImageService.decode_url` fetches bytes and
        :meth:`~app.data.create_database.Database.add_art` persists metadata and binary data.

        Re-checks ``art`` inside the loop to avoid duplicate generation if another writer
        inserted a row after the initial query.

        Args:
            amount: Cap on candidate articles to attempt this call.
            artist: :class:`~app.data.enum_classes.Artist` value with a concrete implementation
                class (e.g. ``SpectraVeritas``, ``FRA1``).
            model: :class:`~app.data.enum_classes.ImageModel`; stored on the ``art`` row for provenance.

        Returns:
            Dict with:

            - ``success`` (``bool``): Currently always ``True`` for implemented paths (including
              when the database or image service is missing — then counts are zero and
              ``message`` explains the gap). Check ``images_generated`` / ``results`` for substance.
            - ``message`` (``str``): Operator-facing summary.
            - ``images_generated`` (``int``), ``images_failed`` (``int``)
            - ``results`` (``list[dict]``): Per article — ``article_id``, ``status`` (``success`` /
              ``failed`` / ``skipped``), plus ``art_id`` / ``title`` or ``error`` / ``reason``.

        Raises:
            ValueError: ``artist`` enum has no mapped implementation class.
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

    def run_extract_anchors(
        self,
        youtube_id: str,
        *,
        extractor: Extractor = Extractor.GEMMA_NYE,
        text_model: Optional[GeminiModel] = None,
    ) -> Dict[str, Any]:
        """Run a selected extractor over a stored transcript.

        Synchronous (the underlying Gemini calls are blocking I/O). The route
        handler awaits this in a threadpool via FastAPI's default sync-handler
        behavior, so per-request blocking is fine for a manually-triggered
        endpoint. Do not call this from inside an existing async event loop.

        Args:
            youtube_id: The YouTube video id of the transcript to extract.
                Must exist in the ``transcripts`` table.
            extractor: Which agent extractor to run (Swagger dropdown).
                Today only :data:`~app.data.enum_classes.Extractor.GEMMA_NYE`
                is wired; unknown values return ``unknown_extractor``.
            text_model: Optional Gemini model override for all four LLM
                passes. When omitted, the extractor's class default applies
                (``GEMINI_3_PRO_PREVIEW`` for Gemma). Use a Flash variant
                when billing is off or quotas are tight.

        Returns:
            Dict with:

            - ``success`` (``bool``): ``False`` when dependencies are missing,
              the transcript isn't found, the transcript has no content, or
              extraction failed.
            - ``message`` (``str``): Summary for operators.
            - ``youtube_id`` (``str``): Echoed back for log correlation.
            - ``extractor`` (``str``): Echo of the chosen extractor display name.
            - ``run_id`` (``str``, optional): Extraction run UUID; present on
              successful extractions and on extractor-returned failures.
            - ``provider`` / ``model`` (``str``, optional): The text-LLM
              provider + model id used for the extract pass.
            - ``anchors_inserted`` (``int``): Factual-anchor rows written to
              the ``anchors`` table. Excludes summary-bullet rows.
            - ``bullets_inserted`` (``int``): Executive-summary bullet rows
              written to the ``anchors`` table (one row per bullet).
            - ``removed_drafts_inserted`` (``int``): Audit rows written to
              ``fact_check_removals`` for draft anchors the fact-check pass
              dropped as fabricated.
            - ``primary_committee`` (``str``, optional): Committee enum value
              the extractor classified the meeting under.
            - ``error`` (``str``, optional): Present when ``success`` is
              ``False``; carries a short cause code.
        """
        db = self._database
        anchor_manager = self._anchor_manager
        if not db:
            return {
                "success": False,
                "message": "Database not available",
                "youtube_id": youtube_id,
                "error": "Database not initialized",
            }
        if not anchor_manager:
            return {
                "success": False,
                "message": "AnchorManager not wired into PipelineService",
                "youtube_id": youtube_id,
                "error": "AnchorManager not available",
            }
        if extractor != Extractor.GEMMA_NYE:
            return {
                "success": False,
                "message": f"Extractor {extractor.value!r} is not wired yet",
                "youtube_id": youtube_id,
                "extractor": extractor.value,
                "error": "unknown_extractor",
            }
        gemma = self._gemma_extractor
        if not gemma:
            return {
                "success": False,
                "message": "Gemma extractor not wired into PipelineService",
                "youtube_id": youtube_id,
                "extractor": extractor.value,
                "error": "GemmaExtractor not available",
            }

        try:
            db.cursor.execute(
                "SELECT content, yt_published_date FROM transcripts WHERE youtube_id = ? LIMIT 1",
                (youtube_id,),
            )
            row = db.cursor.fetchone()
        except Exception as e:
            logger.exception(
                "Pipeline extract_anchors: transcript lookup failed yt=%s", youtube_id
            )
            return {
                "success": False,
                "message": f"Transcript lookup failed: {e}",
                "youtube_id": youtube_id,
                "error": str(e),
            }
        if not row:
            return {
                "success": False,
                "message": f"No transcript found for youtube_id={youtube_id}",
                "youtube_id": youtube_id,
                "error": "transcript_not_found",
            }
        transcript_content, yt_published_date = row[0], row[1]
        if not transcript_content or not transcript_content.strip():
            return {
                "success": False,
                "message": f"Transcript for youtube_id={youtube_id} is empty",
                "youtube_id": youtube_id,
                "error": "transcript_empty",
            }
        meeting_date = (yt_published_date or "")[:10] or "unknown"

        model_override = text_model  # GeminiModel member or None
        logger.info(
            "Pipeline extract_anchors: starting yt=%s extractor=%s model=%s "
            "transcript_chars=%d meeting_date=%s",
            youtube_id,
            extractor.value,
            model_override.value
            if model_override
            else (gemma.MODEL.value if gemma.MODEL is not None else "default"),
            len(transcript_content),
            meeting_date,
        )
        try:
            envelope = gemma.extract(
                transcript=transcript_content,
                youtube_video_id=youtube_id,
                meeting_date=meeting_date,
                model=model_override,
            )
        except Exception as e:
            logger.exception(
                "Pipeline extract_anchors: %s raised yt=%s",
                extractor.value,
                youtube_id,
            )
            return {
                "success": False,
                "message": f"{extractor.value} extraction raised: {e}",
                "youtube_id": youtube_id,
                "extractor": extractor.value,
                "error": str(e),
            }

        if not envelope.get("success"):
            logger.warning(
                "Pipeline extract_anchors: %s returned success=False yt=%s msg=%s",
                extractor.value,
                youtube_id,
                envelope.get("message"),
            )
            return {
                "success": False,
                "message": envelope.get("message") or f"{extractor.value} extraction failed",
                "youtube_id": youtube_id,
                "extractor": extractor.value,
                "run_id": envelope.get("run_id"),
                "provider": envelope.get("provider"),
                "model": envelope.get("model"),
                "error": envelope.get("message") or "extraction_failed",
            }

        data = envelope.get("data") or {}
        run_id = envelope.get("run_id")
        try:
            anchor_manager.insert_from_envelope(
                youtube_id=youtube_id,
                run_id=run_id,
                envelope=data,
                extractor_name=gemma.FULL_NAME,
                model=envelope.get("model"),
            )
        except Exception as e:
            logger.exception(
                "Pipeline extract_anchors: AnchorManager insert raised yt=%s run_id=%s",
                youtube_id,
                run_id,
            )
            return {
                "success": False,
                "message": f"AnchorManager insert raised (anchors NOT persisted): {e}",
                "youtube_id": youtube_id,
                "extractor": extractor.value,
                "run_id": run_id,
                "provider": envelope.get("provider"),
                "model": envelope.get("model"),
                "error": str(e),
            }

        anchors_inserted = len(data.get("factual_anchor_items") or [])
        bullets_inserted = len(data.get("executive_summary_bullets") or [])
        removed_drafts_inserted = len(data.get("removed_drafts") or [])
        logger.info(
            "Pipeline extract_anchors: complete yt=%s extractor=%s run_id=%s "
            "anchors=%d bullets=%d removed=%d",
            youtube_id,
            extractor.value,
            run_id,
            anchors_inserted,
            bullets_inserted,
            removed_drafts_inserted,
        )
        return {
            "success": True,
            "message": "Extraction complete",
            "youtube_id": youtube_id,
            "extractor": extractor.value,
            "run_id": run_id,
            "provider": envelope.get("provider"),
            "model": envelope.get("model"),
            "anchors_inserted": anchors_inserted,
            "bullets_inserted": bullets_inserted,
            "removed_drafts_inserted": removed_drafts_inserted,
            "primary_committee": data.get("primary_committee"),
        }
