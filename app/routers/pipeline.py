"""Pipeline run endpoint."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import ArticleType, Artist, ImageModel, Journalist, PipelineQueueMode, Tone

router = APIRouter(tags=["pipeline"])
logger = logging.getLogger(__name__)


@router.post("/pipeline/run")
async def run_data_pipeline(
    amount: int,
    channel_url: Optional[str] = None,
    queue_mode: PipelineQueueMode = PipelineQueueMode.SKIP_WHISPER,
    auto_build: bool = True,
    journalist: Journalist = Journalist.FR_J1,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.NEWS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
    sync_to_wordpress: bool = True,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run the full data pipeline: build queue (or skip), fetch transcripts, write articles, bullet points, images. Optionally sync to WordPress.
    queue_mode: Use Whisper = build queue and use Whisper when needed; Skip Whisper = skip queue build, only process existing queue."""
    logger.info(
        "Pipeline run started: amount=%s queue_mode=%s sync_to_wordpress=%s",
        amount, queue_mode.value, sync_to_wordpress,
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
    artist = Artist.FRA1
    pipeline = deps.pipeline_service
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline service not available",
        )

    aggregated = {
        "success": True,
        "message": "Pipeline run complete",
        "amount": amount,
        "queue_mode": queue_mode.value,
        "queue_build": None,
        "transcript_fetch": None,
        "article_write": None,
        "bullet_points": None,
        "image_generate": None,
        "wordpress_sync": None,
    }

    def log_step_outcome(step_name: str, result: Optional[Dict[str, Any]]) -> None:
        """Emit a compact, consistent log line for each pipeline step outcome."""
        if result is None:
            logger.info("Pipeline step outcome: step=%s status=unknown message=no-result", step_name)
            return

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
            "processed",
            "skipped",
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

    # Fetch WordPress article youtube_ids once: skip these everywhere (don't queue, don't pull transcript)
    on_wp_ids = set()
    if deps.wordpress_sync_service:
        try:
            on_wp_ids = deps.wordpress_sync_service.get_article_youtube_ids()
        except Exception as e:
            logger.warning("Pipeline: get_article_youtube_ids failed (proceeding with empty skip set): %s", e)

    skip_queue_build = queue_mode == PipelineQueueMode.SKIP_WHISPER
    if skip_queue_build:
        aggregated["queue_build"] = {"skipped": True, "message": "Queue build skipped (Skip Whisper mode)"}
        log_step_outcome("queue_build", aggregated["queue_build"])
    else:
        try:
            aggregated["queue_build"] = await pipeline.run_build_queue(
                channel_url, amount, skip_youtube_ids_on_wp=on_wp_ids
            )
            log_step_outcome("queue_build", aggregated["queue_build"])
        except Exception as e:
            aggregated["success"] = False
            aggregated["queue_build"] = {"error": str(e)}
            logger.error(f"Pipeline queue build failed: {e}")
            log_step_outcome("queue_build", aggregated["queue_build"])
            return aggregated

    # When Skip Whisper, do not auto-build queue and only process videos that have captions (exclude Whisper-needed)
    auto_build_for_fetch = auto_build and not skip_queue_build
    include_whisper_items = queue_mode == PipelineQueueMode.USE_WHISPER
    try:
        aggregated["transcript_fetch"] = await pipeline.run_bulk_fetch_transcripts(
            amount, auto_build_for_fetch, channel_url, skip_youtube_ids_on_wp=on_wp_ids, include_whisper_items=include_whisper_items
        )
        log_step_outcome("transcript_fetch", aggregated["transcript_fetch"])
    except Exception as e:
        aggregated["success"] = False
        aggregated["transcript_fetch"] = {"error": str(e)}
        logger.error(f"Pipeline transcript fetch failed: {e}")
        log_step_outcome("transcript_fetch", aggregated["transcript_fetch"])
        return aggregated

    if not aggregated["transcript_fetch"].get("success"):
        aggregated["success"] = False
        logger.error(
            "Pipeline stopping: no transcripts fetched this run: %s",
            aggregated["transcript_fetch"].get("message", "transcripts_fetched=0"),
        )
        return aggregated

    try:
        # Write articles for all transcripts that don't have one (1:1). WordPress skip is only when syncing.
        aggregated["article_write"] = await pipeline.run_bulk_write_articles(
            amount, journalist, tone, article_type, skip_youtube_ids=None
        )
        log_step_outcome("article_write", aggregated["article_write"])
    except Exception as e:
        aggregated["success"] = False
        aggregated["article_write"] = {"error": str(e)}
        logger.error(f"Pipeline article write failed: {e}")
        log_step_outcome("article_write", aggregated["article_write"])
        return aggregated

    try:
        aggregated["bullet_points"] = pipeline.run_bullet_points_batch(amount)
        log_step_outcome("bullet_points", aggregated["bullet_points"])
    except Exception as e:
        aggregated["success"] = False
        aggregated["bullet_points"] = {"error": str(e)}
        logger.error(f"Pipeline bullet points failed: {e}")
        log_step_outcome("bullet_points", aggregated["bullet_points"])
        return aggregated

    try:
        aggregated["image_generate"] = pipeline.run_image_batch(amount, artist, model)
        log_step_outcome("image_generate", aggregated["image_generate"])
    except Exception as e:
        aggregated["success"] = False
        aggregated["image_generate"] = {"error": str(e)}
        logger.error(f"Pipeline image generate failed: {e}")
        log_step_outcome("image_generate", aggregated["image_generate"])
        return aggregated

    if sync_to_wordpress and deps.database:
        wp_svc = deps.wordpress_sync_service
        if wp_svc:
            image_results = (aggregated.get("image_generate") or {}).get("results") or []
            article_ids = [
                r["article_id"]
                for r in image_results
                if r.get("status") == "success" and "article_id" in r
            ]
            synced = 0
            failed = 0
            errors = []
            try:
                if not article_ids:
                    logger.info("Pipeline WordPress sync skipped: no newly imaged articles to sync")
                for aid in article_ids:
                    try:
                        result = wp_svc.sync_one_article(aid)
                        if result.get("success"):
                            synced += 1
                        else:
                            failed += 1
                            err_msg = result.get("error", "Unknown error")
                            errors.append({"article_id": aid, "error": err_msg})
                            logger.warning("Pipeline WordPress sync failed for article %s: %s", aid, err_msg)
                    except Exception as e:
                        failed += 1
                        errors.append({"article_id": aid, "error": str(e)})
                        logger.error("Pipeline WordPress sync raised for article %s: %s", aid, e, exc_info=True)
                aggregated["wordpress_sync"] = {"synced": synced, "failed": failed, "errors": errors}
                log_step_outcome("wordpress_sync", aggregated["wordpress_sync"])
            except Exception as e:
                aggregated["success"] = False
                aggregated["wordpress_sync"] = {"error": str(e), "synced": synced, "failed": failed, "errors": errors}
                logger.error("Pipeline WordPress sync failed: %s", e, exc_info=True)
                log_step_outcome("wordpress_sync", aggregated["wordpress_sync"])
    else:
        aggregated["wordpress_sync"] = {"skipped": True, "message": "WordPress sync skipped"}
        log_step_outcome("wordpress_sync", aggregated["wordpress_sync"])

    transcript_result = aggregated.get("transcript_fetch") or {}
    article_result = aggregated.get("article_write") or {}
    image_result = aggregated.get("image_generate") or {}
    wp_result = aggregated.get("wordpress_sync") or {}
    logger.info(
        "Pipeline run completed: success=%s transcripts_fetched=%s articles_generated=%s images_generated=%s wp_synced=%s wp_failed=%s",
        aggregated.get("success", True),
        transcript_result.get("transcripts_fetched", 0),
        article_result.get("articles_generated", 0),
        image_result.get("images_generated", 0),
        wp_result.get("synced", 0),
        wp_result.get("failed", 0),
    )
    return aggregated
