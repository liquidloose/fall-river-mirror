"""Queue endpoints: build, cleanup, stats, clear."""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.video_queue_manager import VideoQueueManager

router = APIRouter(tags=["queue"])
logger = logging.getLogger(__name__)

# Simple in-memory rate limiting for the queue build endpoint
QUEUE_BUILD_MAX_CALLS = int(os.environ.get("QUEUE_BUILD_RATE_LIMIT", "5"))
QUEUE_BUILD_WINDOW_SECONDS = int(os.environ.get("QUEUE_BUILD_WINDOW_SECONDS", "60"))
_queue_build_call_times: List[float] = []
_queue_build_lock = threading.Lock()


def enforce_queue_build_rate_limit() -> None:
    now = time.time()
    with _queue_build_lock:
        window_start = now - QUEUE_BUILD_WINDOW_SECONDS
        # Drop timestamps that are outside the current window
        while _queue_build_call_times and _queue_build_call_times[0] < window_start:
            _queue_build_call_times.pop(0)

        if len(_queue_build_call_times) >= QUEUE_BUILD_MAX_CALLS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: max {QUEUE_BUILD_MAX_CALLS} queue builds "
                    f"per {QUEUE_BUILD_WINDOW_SECONDS} seconds"
                ),
            )

        _queue_build_call_times.append(now)


@router.post("/queue/build")
async def build_video_queue(
    limit: int = 5,
    channel_url: Optional[str] = None,
    deps: AppDependencies = Depends(AppDependencies),
    _rate_limited: None = Depends(enforce_queue_build_rate_limit),
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


@router.get("/queue/compare-wordpress")
def compare_queue_to_wordpress(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """
    Compare video_queue to WordPress: return queue youtube_ids, WordPress article youtube_ids,
    and which are in both / only in queue / only on WordPress.
    """
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    wp_svc = deps.wordpress_sync_service
    if not wp_svc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WordPress sync service not available",
        )
    cursor = deps.database.cursor
    cursor.execute(
        "SELECT youtube_id, transcript_available FROM video_queue WHERE youtube_id IS NOT NULL ORDER BY youtube_id"
    )
    rows = cursor.fetchall()
    queue_items: List[Dict[str, Any]] = [
        {"youtube_id": row[0], "transcript_available": bool(row[1]) if len(row) > 1 else True}
        for row in rows
    ]
    queue_ids = {row[0] for row in rows if row[0]}
    wp_ids = wp_svc.get_article_youtube_ids()
    in_both = queue_ids & wp_ids
    in_queue_only = queue_ids - wp_ids
    on_wp_only = wp_ids - queue_ids
    return {
        "queue_count": len(queue_ids),
        "wordpress_count": len(wp_ids),
        "in_both_count": len(in_both),
        "in_queue_only_count": len(in_queue_only),
        "on_wp_only_count": len(on_wp_only),
        "queue_youtube_ids": sorted(queue_ids),
        "wordpress_youtube_ids": sorted(wp_ids),
        "in_both": sorted(in_both),
        "in_queue_only": sorted(in_queue_only),
        "on_wp_only": sorted(on_wp_only),
        "queue_items": queue_items,
    }


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
