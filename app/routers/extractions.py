"""Extractor endpoints — run anchor extraction over a stored transcript."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import Extractor, GeminiModel

router = APIRouter(tags=["extractions"])
logger = logging.getLogger(__name__)


@router.post("/extract/anchors/{youtube_id}")
def extract_anchors(
    youtube_id: str,
    extractor: Extractor = Extractor.GEMMA_NYE,
    text_model: Optional[GeminiModel] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Run a selected agent extractor over a stored transcript."""
    pipeline = deps.pipeline_service
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline service not available",
        )

    result = pipeline.run_extract_anchors(
        youtube_id,
        extractor=extractor,
        text_model=text_model,
    )

    if not result.get("success"):
        error_code = result.get("error")
        if error_code == "transcript_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("message")
                or f"No transcript found for youtube_id={youtube_id}",
            )
        if error_code == "unknown_extractor":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message") or error_code,
            )

    return result
