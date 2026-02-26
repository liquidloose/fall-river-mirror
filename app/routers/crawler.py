"""YouTube crawler endpoint."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.dependencies import AppDependencies

router = APIRouter(tags=["crawler"])


@router.get("/yt_crawler/{video_id}", response_model=None)
async def yt_crawler_endpoint(
    video_id: str,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any] | JSONResponse:
    """YouTube crawler endpoint that crawls the archive video page and records information about each video."""
    # Placeholder: integrate YouTubeCrawler when needed
    return {"message": "youtube_crawler.crawl_video(video_id)", "video_id": video_id}
