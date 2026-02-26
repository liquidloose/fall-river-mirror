"""Queue endpoints: build, cleanup, stats, clear."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.video_queue_manager import VideoQueueManager

router = APIRouter(tags=["queue"])
logger = logging.getLogger(__name__)


@router.post("/queue/build")
async def build_video_queue(
    limit: int = 5,
    channel_url: Optional[str] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Build the video queue by discovering videos from a YouTube channel."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        channel_url = channel_url or os.environ.get("DEFAULT_YOUTUBE_CHANNEL_URL", "")
        logger.info(
            f"Building queue from {channel_url} - will continue until {limit} new videos are queued"
        )
        pipeline = deps.pipeline_service
        if not pipeline:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Pipeline service not available",
            )
        return await pipeline.run_build_queue(channel_url, limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build video queue: {str(e)}",
        )


@router.post("/queue/cleanup")
def cleanup_video_queue(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Clean up the video queue by removing videos that already have transcripts."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        tm = deps.transcript_manager
        if not tm:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Transcript manager not available",
            )
        logger.info("Starting video queue cleanup")
        results = tm.cleanup_queue()
        if not results.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results.get("error", "Unknown error during cleanup"),
            )
        logger.info(f"Queue cleanup complete: {results['message']}")
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup video queue: {str(e)}",
        )


@router.get("/queue/stats")
def get_queue_stats(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Get statistics about the current video queue."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        queue_manager = VideoQueueManager(deps.database)
        try:
            stats = queue_manager.get_queue_stats()
            return {"success": True, "stats": stats}
        finally:
            queue_manager.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get queue stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue stats: {str(e)}",
        )


@router.delete("/queue/clear")
def clear_video_queue(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Delete all videos from the video queue."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        logger.info("Starting video queue clear (deleting all entries)")
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM video_queue")
        count_before = cursor.fetchone()[0]
        cursor.execute("DELETE FROM video_queue")
        db.conn.commit()
        logger.info(f"Cleared video queue: removed {count_before} videos")
        return {
            "success": True,
            "message": "Successfully cleared video queue",
            "deleted_count": count_before,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear video queue: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear video queue: {str(e)}",
        )
