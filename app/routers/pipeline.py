"""Pipeline run endpoint."""

import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import AppDependencies
from app.data.enum_classes import (
    ArticleType,
    Artist,
    Extractor,
    ImageModel,
    Journalist,
    PipelineQueueMode,
    TextModel,
    Tone,
    resolve_gemini_text_model,
)
from app.services.pipeline_profiler import PipelineProfiler
from app.agent_kit.utility_classes import run_logging

router = APIRouter(tags=["pipeline"])
logger = logging.getLogger(__name__)


@router.post("/pipeline/run")
async def run_data_pipeline(
    amount: int,
    channel_url: Optional[str] = None,
    queue_mode: PipelineQueueMode = PipelineQueueMode.USE_WHISPER,
    auto_build: bool = Query(
        default=True,
        description=(
            "Top-up behavior for transcript fetch when queue is short. "
            "When true and the queue holds fewer caption-eligible videos than "
            "`amount`, the pipeline auto-builds missing queue items up to `amount` "
            "before fetching transcripts. When false, only already-queued items "
            "are fetched. Under Skip Whisper, the initial queue build is still "
            "skipped, but auto_build may top up caption-eligible items during fetch."
        ),
    ),
    journalist: Journalist = Journalist.FR_J1,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.SEQUENTIAL_NEWS,
    extractor: Extractor = Extractor.GEMMA_NYE,
    artist: Artist = Artist.FRA1,
    extractor_text_model: Optional[TextModel] = Query(
        default=TextModel.GEMINI_2_5_PRO,
        description=(
            "Text model used by the extractor stage when converting transcripts "
            "into anchor envelopes. Must resolve to a Gemini model for this stage."
        ),
    ),
    journalist_text_model: Optional[TextModel] = Query(
        default=TextModel.GEMINI_2_5_PRO,
        description=(
            "Text model used by the journalist stage to write article body content "
            "from extracted anchors."
        ),
    ),
    image_model: Optional[ImageModel] = Query(
        default=ImageModel.GPT_IMAGE_1,
        description=(
            "Image generation model used for article cover images in the "
            "image-generation stage."
        ),
    ),
    snippet_text_model: Optional[TextModel] = Query(
        default=TextModel.GEMINI_2_5_FLASH,
        description=(
            "Text model used to condense the article context into an image prompt "
            "snippet before calling the image model."
        ),
    ),
    sync_to_wordpress: bool = True,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run the full data pipeline end-to-end.

    Stages (in order): build queue (or skip) → fetch transcripts → extract
    anchors → write articles → bullet points → cover images → optional
    WordPress sync.

    Parameters
    ----------
    - **amount**: Target number of items to process per stage (e.g. number of
      transcripts to fetch, articles to write).
    - **channel_url**: YouTube channel to source new videos from. Falls back
      to the ``DEFAULT_YOUTUBE_CHANNEL_URL`` env var when omitted.
    - **queue_mode**:
      - ``Use Whisper`` *(default)* — build the queue from the channel, then fetch
        transcripts; use Whisper for videos that lack native captions.
      - ``Skip Whisper`` — do **not** build the queue from the
        channel, and only process videos that already have captions
        (Whisper-needed items are excluded for this run).
    - **auto_build**: Top-up safety net for the transcript-fetch stage. When
      ``True`` and the queue holds fewer caption-eligible videos than
      ``amount``, the pipeline scrapes ``channel_url`` to add the shortfall
      before fetching (newly queued items still respect caption availability).
      When ``False``, only videos already in the queue are processed. Under
      ``Skip Whisper``, the initial queue build is still skipped, but
      ``auto_build`` may still top up caption-eligible items during fetch.
    - **extractor / extractor_text_model**: Extractor persona and optional
      unified text model override used for anchor extraction. The extractor
      stage only accepts Gemini-backed model values.
    - **journalist / tone / article_type**: Persona, voice, and format
      passed to the AI journalist used for the article-writing stage.
    - **journalist_text_model**: Optional override for which text-LLM
      provider + model the journalist uses to write article bodies.
    - **image_model**: Image-generation model used for the cover-art stage.
    - **snippet_text_model**: Optional text model for artist snippet
      condensation before image prompting.
    - **sync_to_wordpress**: When ``True``, push newly imaged articles to
      WordPress after generation; when ``False``, skip the sync step.
    """
    logger.info(
        "Pipeline run started: amount=%s queue_mode=%s sync_to_wordpress=%s",
        amount,
        queue_mode.value,
        sync_to_wordpress,
    )
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be a positive integer",
        )
    channel_url = channel_url or os.environ.get("DEFAULT_YOUTUBE_CHANNEL_URL", "")
    pipeline = deps.pipeline_service
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline service not available",
        )
    try:
        resolve_gemini_text_model(
            extractor_text_model,
            field_name="extractor_text_model",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    resolved_journalist_text_model = journalist_text_model
    resolved_image_model = image_model or ImageModel.GPT_IMAGE_1

    profiler = PipelineProfiler(
        pipeline_run_id=str(uuid.uuid4()),
        params={
            "amount": amount,
            "queue_mode": queue_mode.value,
            "sync_to_wordpress": sync_to_wordpress,
        },
    )
    profiler.mark_received()

    aggregated = {
        "success": True,
        "message": "Pipeline run complete",
        "amount": amount,
        "queue_mode": queue_mode.value,
        "model_selection": {
            "extractor": extractor.value,
            "artist": artist.value,
            "extractor_text_model": (
                extractor_text_model.value if extractor_text_model else None
            ),
            "journalist_text_model": (
                resolved_journalist_text_model.value
                if resolved_journalist_text_model
                else None
            ),
            "snippet_text_model": (
                snippet_text_model.value if snippet_text_model else None
            ),
            "image_model": resolved_image_model.value,
        },
        "queue_build": None,
        "transcript_fetch": None,
        "anchor_extract": None,
        "article_write": None,
        "bullet_points": None,
        "image_generate": None,
        "wordpress_sync": None,
        "profiler": None,
    }

    def log_step_outcome(step_name: str, result: Optional[Dict[str, Any]]) -> str:
        """Emit a compact, consistent log line for each pipeline step outcome.

        Returns the derived status string so callers can record the same value
        on the profiler stage.
        """
        if result is None:
            logger.info(
                "Pipeline step outcome: step=%s status=unknown message=no-result",
                step_name,
            )
            return "unknown"

        status_value = result.get("success")
        if status_value is None and result.get("skipped") is True:
            status = "skipped"
        elif status_value is True:
            status = "success"
        elif status_value is False:
            status = "no-work-or-failed"
        else:
            status = "unknown"

        details = []
        for key in (
            "transcripts_fetched",
            "transcripts_failed",
            "articles_generated",
            "articles_failed",
            "anchors_extracted",
            "anchors_failed",
            "processed",
            "skipped",
            "skipped_existing",
            "images_generated",
            "images_failed",
            "synced",
            "failed",
        ):
            if key in result:
                details.append(f"{key}={result.get(key)}")

        message = result.get("message") or result.get("error") or "n/a"
        detail_text = " ".join(details) if details else "none"
        logger.info(
            "Pipeline step outcome: step=%s status=%s message=%s details=%s",
            step_name,
            status,
            message,
            detail_text,
        )
        return status

    # Fetch WordPress article youtube_ids once: skip these everywhere (don't queue, don't pull transcript)
    on_wp_ids = set()
    if deps.wordpress_sync_service:
        try:
            on_wp_ids = deps.wordpress_sync_service.get_article_youtube_ids()
        except Exception as e:
            logger.warning(
                "Pipeline: get_article_youtube_ids failed (proceeding with empty skip set): %s",
                e,
            )

    try:
        skip_queue_build = queue_mode == PipelineQueueMode.SKIP_WHISPER
        if skip_queue_build:
            profiler.begin_stage("queue_build")
            aggregated["queue_build"] = {
                "skipped": True,
                "message": "Queue build skipped (Skip Whisper mode)",
            }
            profiler.end_stage(
                "queue_build",
                log_step_outcome("queue_build", aggregated["queue_build"]),
            )
        else:
            profiler.mark_ready()
            profiler.begin_stage("queue_build")
            try:
                aggregated["queue_build"] = await pipeline.run_build_queue(
                    channel_url, amount, skip_youtube_ids_on_wp=on_wp_ids
                )
                profiler.end_stage(
                    "queue_build",
                    log_step_outcome("queue_build", aggregated["queue_build"]),
                )
            except Exception as e:
                aggregated["success"] = False
                aggregated["queue_build"] = {"error": str(e)}
                logger.error(f"Pipeline queue build failed: {e}")
                profiler.end_stage(
                    "queue_build",
                    log_step_outcome("queue_build", aggregated["queue_build"]),
                )
                return aggregated

        # Skip Whisper: no initial queue build; fetch skips Whisper-required items and
        # may still auto-build caption-eligible queue items when auto_build=True.
        auto_build_for_fetch = auto_build
        include_whisper_items = queue_mode == PipelineQueueMode.USE_WHISPER
        profiler.mark_ready()
        profiler.begin_stage("transcript_fetch")
        try:
            aggregated["transcript_fetch"] = await pipeline.run_bulk_fetch_transcripts(
                amount,
                auto_build_for_fetch,
                channel_url,
                skip_youtube_ids_on_wp=on_wp_ids,
                include_whisper_items=include_whisper_items,
            )
            profiler.end_stage(
                "transcript_fetch",
                log_step_outcome("transcript_fetch", aggregated["transcript_fetch"]),
            )
        except Exception as e:
            aggregated["success"] = False
            aggregated["transcript_fetch"] = {"error": str(e)}
            logger.error(f"Pipeline transcript fetch failed: {e}")
            profiler.end_stage(
                "transcript_fetch",
                log_step_outcome("transcript_fetch", aggregated["transcript_fetch"]),
            )
            return aggregated

        if not aggregated["transcript_fetch"].get("success"):
            aggregated["success"] = False
            logger.error(
                "Pipeline stopping: no transcripts fetched this run: %s",
                aggregated["transcript_fetch"].get("message", "transcripts_fetched=0"),
            )
            return aggregated

        profiler.begin_stage("anchor_extract")
        try:
            aggregated["anchor_extract"] = await pipeline.run_bulk_extract_anchors(
                amount,
                extractor=extractor,
                text_model=extractor_text_model,
                skip_youtube_ids=on_wp_ids or None,
            )
            profiler.end_stage(
                "anchor_extract",
                log_step_outcome("anchor_extract", aggregated["anchor_extract"]),
            )
        except Exception as e:
            aggregated["success"] = False
            aggregated["anchor_extract"] = {"error": str(e)}
            logger.error(f"Pipeline anchor extraction failed: {e}")
            profiler.end_stage(
                "anchor_extract",
                log_step_outcome("anchor_extract", aggregated["anchor_extract"]),
            )
            return aggregated

        profiler.begin_stage("article_write")
        try:
            # Write articles for all transcripts that don't have one (1:1). WordPress skip is only when syncing.
            aggregated["article_write"] = await pipeline.run_bulk_write_articles(
                amount,
                journalist,
                tone,
                article_type,
                skip_youtube_ids=None,
                text_model=resolved_journalist_text_model,
            )
            profiler.end_stage(
                "article_write",
                log_step_outcome("article_write", aggregated["article_write"]),
            )
        except Exception as e:
            aggregated["success"] = False
            aggregated["article_write"] = {"error": str(e)}
            logger.error(f"Pipeline article write failed: {e}")
            profiler.end_stage(
                "article_write",
                log_step_outcome("article_write", aggregated["article_write"]),
            )
            return aggregated

        profiler.begin_stage("bullet_points")
        try:
            aggregated["bullet_points"] = pipeline.run_bullet_points_batch(amount)
            profiler.end_stage(
                "bullet_points",
                log_step_outcome("bullet_points", aggregated["bullet_points"]),
            )
        except Exception as e:
            aggregated["success"] = False
            aggregated["bullet_points"] = {"error": str(e)}
            logger.error(f"Pipeline bullet points failed: {e}")
            profiler.end_stage(
                "bullet_points",
                log_step_outcome("bullet_points", aggregated["bullet_points"]),
            )
            return aggregated

        profiler.begin_stage("image_generate")
        try:
            aggregated["image_generate"] = pipeline.run_image_batch(
                amount,
                artist,
                resolved_image_model,
                snippet_text_model=snippet_text_model,
            )
            profiler.end_stage(
                "image_generate",
                log_step_outcome("image_generate", aggregated["image_generate"]),
            )
        except Exception as e:
            aggregated["success"] = False
            aggregated["image_generate"] = {"error": str(e)}
            logger.error(f"Pipeline image generate failed: {e}")
            profiler.end_stage(
                "image_generate",
                log_step_outcome("image_generate", aggregated["image_generate"]),
            )
            return aggregated

        profiler.begin_stage("wordpress_sync")
        if sync_to_wordpress and deps.database:
            wp_svc = deps.wordpress_sync_service
            if wp_svc:
                image_results = (aggregated.get("image_generate") or {}).get(
                    "results"
                ) or []
                article_ids = [
                    r["article_id"]
                    for r in image_results
                    if r.get("status") == "success" and "article_id" in r
                ]
                synced = 0
                skipped_existing = 0
                failed = 0
                errors = []
                try:
                    if not article_ids:
                        logger.info(
                            "Pipeline WordPress sync skipped: no newly imaged articles to sync"
                        )
                    for aid in article_ids:
                        try:
                            _wp_perf = time.perf_counter()
                            result = wp_svc.sync_one_article(aid)
                            _wp_youtube_id = None
                            try:
                                deps.database.cursor.execute(
                                    "SELECT youtube_id FROM articles WHERE id = ? LIMIT 1",
                                    (aid,),
                                )
                                _wp_row = deps.database.cursor.fetchone()
                                if _wp_row:
                                    _wp_youtube_id = _wp_row[0]
                            except Exception:
                                _wp_youtube_id = None
                            run_logging.record_stage(
                                _wp_youtube_id,
                                "wordpress_sync",
                                "WordPress publish",
                                time.perf_counter() - _wp_perf,
                            )
                            if result.get("success") and result.get("skipped"):
                                skipped_existing += 1
                            elif result.get("success"):
                                synced += 1
                            else:
                                failed += 1
                                err_msg = result.get("error", "Unknown error")
                                errors.append({"article_id": aid, "error": err_msg})
                                logger.warning(
                                    "Pipeline WordPress sync failed for article %s: %s",
                                    aid,
                                    err_msg,
                                )
                        except Exception as e:
                            failed += 1
                            errors.append({"article_id": aid, "error": str(e)})
                            logger.error(
                                "Pipeline WordPress sync raised for article %s: %s",
                                aid,
                                e,
                                exc_info=True,
                            )
                    aggregated["wordpress_sync"] = {
                        "synced": synced,
                        "skipped_existing": skipped_existing,
                        "failed": failed,
                        "errors": errors,
                    }
                    profiler.end_stage(
                        "wordpress_sync",
                        log_step_outcome("wordpress_sync", aggregated["wordpress_sync"]),
                    )
                except Exception as e:
                    aggregated["success"] = False
                    aggregated["wordpress_sync"] = {
                        "error": str(e),
                        "synced": synced,
                        "skipped_existing": skipped_existing,
                        "failed": failed,
                        "errors": errors,
                    }
                    logger.error("Pipeline WordPress sync failed: %s", e, exc_info=True)
                    profiler.end_stage(
                        "wordpress_sync",
                        log_step_outcome("wordpress_sync", aggregated["wordpress_sync"]),
                    )
            else:
                aggregated["wordpress_sync"] = {
                    "skipped": True,
                    "message": "WordPress sync skipped (sync service unavailable)",
                }
                profiler.end_stage(
                    "wordpress_sync",
                    log_step_outcome("wordpress_sync", aggregated["wordpress_sync"]),
                )
        else:
            aggregated["wordpress_sync"] = {
                "skipped": True,
                "message": "WordPress sync skipped",
            }
            profiler.end_stage(
                "wordpress_sync",
                log_step_outcome("wordpress_sync", aggregated["wordpress_sync"]),
            )

        transcript_result = aggregated.get("transcript_fetch") or {}
        extract_result = aggregated.get("anchor_extract") or {}
        article_result = aggregated.get("article_write") or {}
        image_result = aggregated.get("image_generate") or {}
        wp_result = aggregated.get("wordpress_sync") or {}
        logger.info(
            "Pipeline run completed: success=%s transcripts_fetched=%s anchors_extracted=%s articles_generated=%s images_generated=%s wp_synced=%s wp_failed=%s",
            aggregated.get("success", True),
            transcript_result.get("transcripts_fetched", 0),
            extract_result.get("anchors_extracted", 0),
            article_result.get("articles_generated", 0),
            image_result.get("images_generated", 0),
            wp_result.get("synced", 0),
            wp_result.get("failed", 0),
        )
        return aggregated
    finally:
        aggregated["profiler"] = profiler.finish(aggregated.get("success", True))
