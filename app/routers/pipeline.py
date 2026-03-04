"""Pipeline run endpoint."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import ArticleType, Artist, ImageModel, Journalist, Tone

router = APIRouter(tags=["pipeline"])
logger = logging.getLogger(__name__)


@router.post("/pipeline/run")
async def run_data_pipeline(
    amount: int,
    channel_url: Optional[str] = None,
    auto_build: bool = True,
    journalist: Journalist = Journalist.FR_J1,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.NEWS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
    sync_to_wordpress: bool = False,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run the full data pipeline: build queue, fetch transcripts, write articles, bullet points, images. Optionally sync to WordPress."""
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
        "queue_build": None,
        "transcript_fetch": None,
        "article_write": None,
        "bullet_points": None,
        "image_generate": None,
        "wordpress_sync": None,
    }

    # Fetch WordPress article youtube_ids once: skip these everywhere (don't queue, don't pull transcript)
    on_wp_ids = set()
    if deps.wordpress_sync_service:
        on_wp_ids = deps.wordpress_sync_service.get_article_youtube_ids()

    try:
        aggregated["queue_build"] = await pipeline.run_build_queue(
            channel_url, amount, skip_youtube_ids_on_wp=on_wp_ids
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["queue_build"] = {"error": str(e)}
        logger.error(f"Pipeline queue build failed: {e}")
        return aggregated

    try:
        aggregated["transcript_fetch"] = await pipeline.run_bulk_fetch_transcripts(
            amount, auto_build, channel_url, skip_youtube_ids_on_wp=on_wp_ids
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["transcript_fetch"] = {"error": str(e)}
        logger.error(f"Pipeline transcript fetch failed: {e}")
        return aggregated

    try:
        # Write articles for all transcripts that don't have one (1:1). WordPress skip is only when syncing.
        aggregated["article_write"] = await pipeline.run_bulk_write_articles(
            amount, journalist, tone, article_type, skip_youtube_ids=None
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["article_write"] = {"error": str(e)}
        logger.error(f"Pipeline article write failed: {e}")
        return aggregated

    try:
        aggregated["bullet_points"] = pipeline.run_bullet_points_batch(amount)
    except Exception as e:
        aggregated["success"] = False
        aggregated["bullet_points"] = {"error": str(e)}
        logger.error(f"Pipeline bullet points failed: {e}")
        return aggregated

    try:
        aggregated["image_generate"] = pipeline.run_image_batch(amount, artist, model)
    except Exception as e:
        aggregated["success"] = False
        aggregated["image_generate"] = {"error": str(e)}
        logger.error(f"Pipeline image generate failed: {e}")
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
            # #region agent log
            try:
                import json
                existing_wp = wp_svc.get_article_youtube_ids()
                db = deps.database
                for aid in article_ids:
                    art = db.get_article_by_id(aid) if db else None
                    yid = (art.get("youtube_id") or "").strip() if art else None
                    already = yid in existing_wp if yid else None
                    open("/code/.cursor/debug.log", "a").write(
                        json.dumps({"hypothesisId": "H2_H3", "location": "pipeline.run_data_pipeline", "message": "wordpress sync candidate", "data": {"article_id": aid, "youtube_id": yid, "already_on_wordpress": already}, "timestamp": __import__("time").time() * 1000}) + "\n"
                    )
            except Exception:
                pass
            # #endregion
            synced = 0
            failed = 0
            errors = []
            for aid in article_ids:
                result = wp_svc.sync_one_article(aid)
                if result.get("success"):
                    synced += 1
                else:
                    failed += 1
                    errors.append({"article_id": aid, "error": result.get("error", "Unknown error")})
                    logger.warning(f"Pipeline WordPress sync failed for article {aid}: {result.get('error')}")
            aggregated["wordpress_sync"] = {"synced": synced, "failed": failed, "errors": errors}

    return aggregated
