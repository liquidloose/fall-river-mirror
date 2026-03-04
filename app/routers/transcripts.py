"""Transcript endpoints: fetch, delete, bulk fetch, list without articles, pending by journalist."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.dependencies import AppDependencies
from app.data.enum_classes import Journalist

router = APIRouter(tags=["transcripts"])
logger = logging.getLogger(__name__)


@router.get("/transcripts/count")
def get_transcript_count(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Get the total count of transcripts. Should match article count (1:1)."""
    if not deps.database:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    try:
        deps.database.cursor.execute("SELECT COUNT(*) FROM transcripts")
        count = deps.database.cursor.fetchone()[0]
        return {
            "total_transcripts": count,
            "message": f"There are {count} transcripts in the database",
        }
    except Exception as e:
        logger.error("Failed to get transcript count: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get transcript count: {str(e)}",
        )


@router.get("/transcript/fetch/{youtube_id}", response_model=None)
def get_transcript_endpoint(
    youtube_id: str,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any] | JSONResponse:
    """Fetch YouTube video transcript. Checks database cache, then fetches from YouTube if not found."""
    logger.info(f"Fetching transcript for YouTube ID {youtube_id}")
    tm = deps.transcript_manager
    if not tm:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcript manager not available",
        )
    return tm.get_transcript(youtube_id)


@router.delete("/transcript/delete/{transcript_id}")
def delete_transcript_endpoint(
    transcript_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Delete a transcript by its ID."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        success = db.delete_transcript_by_id(transcript_id)
        if success:
            logger.info(f"Successfully deleted transcript with ID {transcript_id}")
            return {
                "success": True,
                "message": f"Transcript with ID {transcript_id} deleted successfully",
                "transcript_id": transcript_id,
            }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript with ID {transcript_id} not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete transcript {transcript_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete transcript: {str(e)}",
        )


@router.post("/transcript/fetch/{amount}")
async def bulk_fetch_transcripts(
    amount: int,
    auto_build: bool = Body(True),
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Bulk fetch and store transcripts for queued YouTube videos."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        logger.info(f"Starting bulk transcript fetch for {amount} videos from queue")
        pipeline = deps.pipeline_service
        if not pipeline:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Pipeline service not available",
            )
        return await pipeline.run_bulk_fetch_transcripts(amount, auto_build, None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk transcript fetch failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk transcript fetch failed: {str(e)}",
        )


@router.get("/transcripts/without-articles")
def get_transcripts_without_articles(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """List transcripts that have no article."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        cursor = db.cursor
        cursor.execute(
            """
            SELECT t.id, t.youtube_id, t.committee, t.meeting_date, t.video_title
            FROM transcripts t
            WHERE NOT EXISTS (
                SELECT 1 FROM articles a WHERE a.transcript_id = t.id
            )
            ORDER BY t.id
            """
        )
        rows = cursor.fetchall()
        transcripts = [
            {"id": r[0], "youtube_id": r[1], "committee": r[2], "meeting_date": r[3], "video_title": r[4]}
            for r in rows
        ]
        return {"success": True, "count": len(transcripts), "transcripts": transcripts}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get transcripts without articles failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get transcripts without articles failed: {str(e)}",
        )


@router.get("/transcripts/pending/{journalist}")
def get_pending_transcripts(
    journalist: Journalist,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Get transcripts that don't have an article from a specific journalist."""
    from app.content_department.ai_journalists.aurelius_stone import AureliusStone
    from app.content_department.ai_journalists.fr_j1 import FRJ1

    try:
        db = deps.database
        jm = deps.journalist_manager
        if not db or not jm:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
            Journalist.FR_J1: FRJ1,
        }
        journalist_class = journalist_classes.get(journalist)
        if not journalist_class:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journalist '{journalist.value}' not implemented yet",
            )
        journalist_instance = journalist_class()
        journalist_data = jm.get_journalist(journalist_instance.FULL_NAME)
        if not journalist_data:
            jm.upsert_journalist(
                full_name=journalist_instance.FULL_NAME,
                first_name=journalist_instance.FIRST_NAME,
                last_name=journalist_instance.LAST_NAME,
                bio=journalist_instance.get_bio(),
                description=journalist_instance.get_description(),
            )
            journalist_data = jm.get_journalist(journalist_instance.FULL_NAME)
            if not journalist_data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create or retrieve journalist '{journalist_instance.FULL_NAME}'",
                )
        journalist_id = journalist_data["id"]
        cursor = db.cursor
        cursor.execute(
            """SELECT t.id, t.youtube_id, t.committee
               FROM transcripts t
               LEFT JOIN articles a ON t.id = a.transcript_id AND a.journalist_id = ?
               WHERE a.id IS NULL
               ORDER BY t.id""",
            (journalist_id,),
        )
        rows = cursor.fetchall()
        meetings = [
            {"transcript_id": row[0], "youtube_id": row[1], "meeting": row[2]}
            for row in rows
        ]
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        total_transcripts = cursor.fetchone()[0]
        covered = total_transcripts - len(meetings)
        return {
            "journalist": journalist.value,
            "summary": f"{journalist.value} has written articles for {covered} of {total_transcripts} meetings. {len(meetings)} meetings have no article from this journalist yet.",
            "articles_written": covered,
            "awaiting_article": len(meetings),
            "total_meetings": total_transcripts,
            "meetings_without_article": meetings,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pending transcripts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending transcripts: {str(e)}",
        )
