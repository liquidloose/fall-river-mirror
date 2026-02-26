"""Image and art endpoints: generate, get, delete, regenerate, cleanup."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.dependencies import AppDependencies
from app.data.enum_classes import Artist, ImageModel
from app.content_department.ai_artists.spectra_veritas import SpectraVeritas
from app.content_department.ai_artists.fra1 import FRA1

router = APIRouter(tags=["images"])
logger = logging.getLogger(__name__)


@router.post("/image/generate/batch/{artist_name}/{amount}")
def bulk_generate_images(
    amount: int,
    artist_name: Artist = Artist.SPECTRA_VERITAS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Bulk generate images for articles that have bullet points but no existing art."""
    try:
        if not deps.database:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        pipeline = deps.pipeline_service
        if not pipeline:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Pipeline service not available",
            )
        logger.info(
            f"Starting bulk image generation: {amount} images, "
            f"artist={artist_name.value}, model={model.value}"
        )
        return pipeline.run_image_batch(amount, artist_name, model)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk image generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk image generation failed: {str(e)}",
        )


@router.post("/image/generate/{artist_name}/{article_id}")
def generate_image(
    artist_name: Artist,
    article_id: int,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Generate an image for an article using the specified artist and model."""
    artist_classes = {Artist.SPECTRA_VERITAS: SpectraVeritas, Artist.FRA1: FRA1}
    artist_class = artist_classes.get(artist_name)
    if not artist_class:
        available_artists = [a.value for a in Artist]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artist '{artist_name.value}' not found. Available artists: {available_artists}",
        )
    db = deps.database
    image_svc = deps.image_service
    if not db or not image_svc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database or image service not available",
        )
    article = db.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID {article_id} not found",
        )
    cursor = db.cursor
    cursor.execute("SELECT id FROM art WHERE article_id = ?", (article_id,))
    existing_art = cursor.fetchone()
    if existing_art:
        return {
            "image_url": None,
            "error": f"Article {article_id} already has art (art_id: {existing_art[0]}). Use DELETE /image/delete/{existing_art[0]} first to regenerate.",
            "article_id": article_id,
            "existing_art_id": existing_art[0],
        }
    bullet_points = article.get("bullet_points")
    if not bullet_points:
        return {
            "image_url": None,
            "error": f"Article {article_id} has no bullet points. Generate bullet points first using PATCH /article/{article_id}/bullet-points",
            "article_id": article_id,
        }
    artist_instance = artist_class()
    image_result = artist_instance.generate_image(
        title=article["title"],
        bullet_points=bullet_points,
        model=model.value,
    )
    if image_result.get("image_url"):
        try:
            image_data = image_svc.decode_url(image_result["image_url"])
            art_id = db.add_art(
                prompt=image_result["prompt_used"],
                image_url=None,
                image_data=image_data,
                medium=image_result.get("medium"),
                aesthetic=image_result.get("aesthetic"),
                title=article["title"],
                artist_name=image_result.get("artist"),
                snippet=image_result.get("snippet"),
                transcript_id=article.get("transcript_id"),
                article_id=article_id,
                model=model.value,
            )
            image_result["art_id"] = art_id
        except HTTPException as e:
            image_result["error"] = e.detail
    return image_result


@router.get("/image/{art_id}")
def get_art_image(
    art_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Response:
    """Serve the image for an art record."""
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    art = db.get_art_by_id(art_id)
    if not art or not art.get("image_data"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image for art ID {art_id} not found",
        )
    return Response(content=art["image_data"], media_type="image/png")


@router.delete("/image/delete/{art_id}")
def delete_art_endpoint(
    art_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Delete an art record by its ID."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        success = db.delete_art_by_id(art_id)
        if success:
            logger.info(f"Successfully deleted art with ID {art_id}")
            return {"success": True, "message": f"Art with ID {art_id} deleted successfully", "art_id": art_id}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Art with ID {art_id} not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete art {art_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete art: {str(e)}",
        )


@router.delete("/art/delete-all")
def delete_all_art_endpoint(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Delete ALL art records from the database."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        deleted_count = db.delete_all_art()
        logger.info(f"Deleted all art: {deleted_count} records")
        return {"success": True, "message": "Successfully deleted all art records", "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"Failed to delete all art: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete all art: {str(e)}",
        )


@router.patch("/image/{art_id}/regenerate")
def regenerate_art_image(
    art_id: int,
    artist_name: Artist = Artist.SPECTRA_VERITAS,
    model: ImageModel = ImageModel.GPT_IMAGE_1,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Regenerate the image for an existing art record."""
    try:
        db = deps.database
        image_svc = deps.image_service
        if not db or not image_svc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        art = db.get_art_by_id(art_id)
        if not art:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Art with ID {art_id} not found",
            )
        article_id = art.get("article_id")
        if not article_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Art {art_id} has no linked article",
            )
        article = db.get_article_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Linked article {article_id} not found",
            )
        bullet_points = article.get("bullet_points")
        if not bullet_points:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Article {article_id} has no bullet points. Generate bullet points first using PATCH /article/{article_id}/bullet-points",
            )
        artist_classes = {Artist.SPECTRA_VERITAS: SpectraVeritas, Artist.FRA1: FRA1}
        artist_class = artist_classes.get(artist_name)
        if not artist_class:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Artist '{artist_name.value}' not implemented",
            )
        artist_instance = artist_class()
        logger.info(f"Regenerating image for art ID {art_id} (article: {article_id})")
        image_result = artist_instance.generate_image(
            title=article["title"],
            bullet_points=bullet_points,
            model=model.value,
        )
        if image_result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image generation failed: {image_result['error']}",
            )
        if not image_result.get("image_url"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No image URL returned from generation",
            )
        image_data = image_svc.decode_url(image_result["image_url"])
        success = db.update_art_image(
            art_id=art_id,
            prompt=image_result["prompt_used"],
            image_data=image_data,
            medium=image_result.get("medium"),
            aesthetic=image_result.get("aesthetic"),
            model=model.value,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update art record",
            )
        logger.info(f"Successfully regenerated image for art ID {art_id}")
        return {
            "success": True,
            "art_id": art_id,
            "article_id": article_id,
            "title": article["title"],
            "model": model.value,
            "medium": image_result.get("medium"),
            "aesthetic": image_result.get("aesthetic"),
            "prompt_used": image_result["prompt_used"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate art image {art_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate art image: {str(e)}",
        )


@router.delete("/art/cleanup-duplicates")
def cleanup_duplicate_art(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Find and delete duplicate art records for articles. Keeps the oldest per article."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        cursor = db.cursor
        cursor.execute(
            """SELECT article_id, COUNT(*) as count
               FROM art
               WHERE article_id IS NOT NULL
               GROUP BY article_id
               HAVING COUNT(*) > 1"""
        )
        duplicates = cursor.fetchall()
        if not duplicates:
            return {
                "success": True,
                "message": "No duplicate art records found",
                "articles_with_duplicates": 0,
                "total_deleted": 0,
                "deleted_art_ids": [],
            }
        deleted_art_ids = []
        articles_processed = 0
        for row in duplicates:
            article_id = row[0]
            cursor.execute(
                """SELECT id, created_date FROM art WHERE article_id = ? ORDER BY created_date ASC""",
                (article_id,),
            )
            art_records = cursor.fetchall()
            if len(art_records) > 1:
                for art_record in art_records[1:]:
                    aid = art_record[0]
                    if db.delete_art_by_id(aid):
                        deleted_art_ids.append(aid)
                        logger.info(f"Deleted duplicate art ID {aid} for article {article_id}")
                articles_processed += 1
        return {
            "success": True,
            "message": f"Cleaned up duplicates for {articles_processed} articles",
            "articles_with_duplicates": articles_processed,
            "total_deleted": len(deleted_art_ids),
            "deleted_art_ids": deleted_art_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup duplicate art: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup duplicate art: {str(e)}",
        )
