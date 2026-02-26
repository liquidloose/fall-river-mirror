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

    try:
        aggregated["queue_build"] = await pipeline.run_build_queue(channel_url, amount)
    except Exception as e:
        aggregated["success"] = False
        aggregated["queue_build"] = {"error": str(e)}
        logger.error(f"Pipeline queue build failed: {e}")
        return aggregated

    try:
        aggregated["transcript_fetch"] = await pipeline.run_bulk_fetch_transcripts(
            amount, auto_build, channel_url
        )
    except Exception as e:
        aggregated["success"] = False
        aggregated["transcript_fetch"] = {"error": str(e)}
        logger.error(f"Pipeline transcript fetch failed: {e}")
        return aggregated

    try:
        aggregated["article_write"] = await pipeline.run_bulk_write_articles(
            amount, journalist, tone, article_type
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
