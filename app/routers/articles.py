"""Article endpoints: CRUD, generate, write, bullet points, strip tags."""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import (
    ArticleType,
    CreateArticleRequest,
    PartialUpdateRequest,
    Tone,
    Journalist,
)
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_journalists.fr_j1 import FRJ1

router = APIRouter(tags=["articles"])
logger = logging.getLogger(__name__)


@router.get("/articles/count")
async def get_article_count(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Get the total count of articles."""
    try:
        articles_db = deps.articles_db
        count = len(articles_db)
        logger.info(f"Article count: {count}")
        return {"total_articles": count, "message": f"There are {count} articles in the database"}
    except Exception as e:
        logger.error(f"Failed to get article count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get article count: {str(e)}",
        )


@router.post("/articles/strip-h1-tags")
async def strip_h1_tags_from_articles(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Strip all H1 tags (and their content) from all articles."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not initialized",
            )
        all_articles = db.get_all_articles()
        h1_pattern = re.compile(r"<h1[^>]*>.*?</h1>", re.DOTALL | re.IGNORECASE)
        modified_count = 0
        modified_ids = []
        articles_db = deps.articles_db
        for article in all_articles:
            content = article.get("content", "")
            if content and h1_pattern.search(content):
                new_content = h1_pattern.sub("", content)
                new_content = re.sub(r"\n\s*\n\s*\n", "\n\n", new_content)
                if db.update_article_content(article["id"], new_content):
                    modified_count += 1
                    modified_ids.append(article["id"])
                    if article["id"] in articles_db:
                        articles_db[article["id"]]["content"] = new_content
        logger.info(f"Stripped H1 tags from {modified_count} articles")
        return {
            "message": "Successfully processed articles",
            "articles_modified": modified_count,
            "modified_article_ids": modified_ids,
            "total_articles_scanned": len(all_articles),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to strip H1 tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to strip H1 tags: {str(e)}",
        )


@router.post("/articles/strip-fall-river-from-titles")
async def strip_fall_river_from_titles(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Remove 'Fall River' from all article titles."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not initialized",
            )
        all_articles = db.get_all_articles()
        fall_river_pattern = re.compile(r"\bFall River'?s?\b[:\s]*", re.IGNORECASE)
        modified_count = 0
        modified_articles = []
        articles_db = deps.articles_db
        for article in all_articles:
            title = article.get("title", "")
            if title and fall_river_pattern.search(title):
                new_title = fall_river_pattern.sub("", title)
                new_title = re.sub(r"\s+", " ", new_title).strip()
                if new_title and new_title[0].islower():
                    new_title = new_title[0].upper() + new_title[1:]
                if new_title and db.update_article_title(article["id"], new_title):
                    modified_count += 1
                    modified_articles.append({"id": article["id"], "old_title": title, "new_title": new_title})
                    if article["id"] in articles_db:
                        articles_db[article["id"]]["title"] = new_title
        logger.info(f"Removed 'Fall River' from {modified_count} article titles")
        return {
            "message": "Successfully processed articles",
            "articles_modified": modified_count,
            "modified_articles": modified_articles,
            "total_articles_scanned": len(all_articles),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to strip Fall River from titles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to strip Fall River from titles: {str(e)}",
        )


@router.get("/articles/", response_model=List[Dict[str, Any]])
async def get_all_articles(
    skip: int = 0,
    limit: int = 100,
    article_type: Optional[ArticleType] = None,
    tone: Optional[Tone] = None,
    committee: Optional[str] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> List[Dict[str, Any]]:
    """Retrieve all articles with optional filtering."""
    try:
        articles_db = deps.articles_db
        articles = list(articles_db.values())
        if article_type:
            articles = [a for a in articles if a.get("article_type") == article_type.value]
        if tone:
            articles = [a for a in articles if a.get("tone") == tone.value]
        if committee:
            articles = [a for a in articles if a.get("committee") == committee]
        articles = articles[skip : skip + limit]
        logger.info(f"Retrieved {len(articles)} articles")
        return articles
    except Exception as e:
        logger.error(f"Failed to retrieve articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}",
        )


@router.get("/articles/{article_id}", response_model=Dict[str, Any])
async def get_article(
    article_id: str,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Retrieve a specific article by ID."""
    try:
        articles_db = deps.articles_db
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )
        logger.info(f"Retrieved article with ID: {article_id}")
        return articles_db[article_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve article: {str(e)}",
        )


@router.delete("/article/{article_id}")
def delete_article_endpoint(
    article_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Delete an article and its corresponding image."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database not available",
            )
        article = db.get_article_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )
        art_deleted_count = db.delete_art_by_article_id(article_id)
        success = db.delete_article_by_id(article_id)
        if success:
            logger.info(f"Successfully deleted article {article_id} and {art_deleted_count} linked image(s)")
            return {
                "success": True,
                "message": f"Article {article_id} and linked images deleted successfully",
                "article_id": article_id,
                "images_deleted": art_deleted_count,
            }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete article {article_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete article: {str(e)}",
        )


@router.delete("/articles/remove-duplicate-per-transcript")
def remove_duplicate_articles_per_transcript(
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Find transcripts with more than one article and delete the extra article(s)."""
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
            SELECT a.id, a.transcript_id
            FROM articles a
            JOIN (
                SELECT transcript_id, MIN(id) AS keep_id
                FROM articles
                WHERE transcript_id IS NOT NULL
                GROUP BY transcript_id
                HAVING COUNT(*) > 1
            ) sub ON a.transcript_id = sub.transcript_id AND a.id != sub.keep_id
            ORDER BY a.id
            """
        )
        rows = cursor.fetchall()
        to_delete = [r[0] for r in rows]
        transcripts_affected = len(set(r[1] for r in rows))
        if not to_delete:
            return {
                "success": True,
                "message": "No duplicate articles found (each transcript has at most one article).",
                "transcripts_affected": 0,
                "articles_deleted": 0,
                "art_deleted": 0,
                "deleted_article_ids": [],
            }
        articles_deleted = 0
        art_deleted = 0
        for aid in to_delete:
            art_deleted += db.delete_art_by_article_id(aid)
            if db.delete_article_by_id(aid):
                articles_deleted += 1
        logger.info(f"Removed duplicate articles: {articles_deleted} articles, {art_deleted} art records; ids={to_delete}")
        return {
            "success": True,
            "message": f"Deleted {articles_deleted} duplicate article(s) from {transcripts_affected} transcript(s), and {art_deleted} linked art record(s).",
            "transcripts_affected": transcripts_affected,
            "articles_deleted": articles_deleted,
            "art_deleted": art_deleted,
            "deleted_article_ids": to_delete,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove duplicate articles failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remove duplicate articles failed: {str(e)}",
        )


@router.post("/article/generate/{journalist}/{tone}/{article_type}/{transcript_id}")
def generate_article_from_strings(
    journalist: Journalist,
    tone: Tone,
    article_type: ArticleType,
    transcript_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Generate article using path parameters. Saves to database."""
    try:
        db = deps.database
        jm = deps.journalist_manager
        if not db or not jm:
            raise HTTPException(status_code=500, detail="Database not available")
        transcript_data = db.get_transcript_by_id(int(transcript_id))
        if not transcript_data:
            raise HTTPException(status_code=404, detail=f"No transcript found with ID {transcript_id}")
        transcript_content = transcript_data[3]
        journalist_instance = AureliusStone()
        base_context = journalist_instance.load_context(tone=tone, article_type=article_type)
        full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
        article_result = journalist_instance.generate_article(full_context, "")
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
                raise HTTPException(status_code=500, detail=f"Failed to create or retrieve journalist '{journalist_instance.FULL_NAME}'")
        journalist_id = journalist_data["id"]
        committee = transcript_data[1]
        youtube_id = transcript_data[2]
        db.add_article(
            committee=committee,
            youtube_id=youtube_id,
            journalist_id=journalist_id,
            content=article_result["content"],
            transcript_id=transcript_id,
            date=datetime.now().isoformat(),
            article_type=article_type.value,
            tone=tone.value,
            title=article_result.get("title", "Untitled Article"),
        )
        logger.info(f"Article generated successfully by {journalist_instance.NAME} using transcript ID {transcript_id}")
        return {
            "journalist": journalist_instance.NAME,
            "context": full_context,
            "title": article_result.get("title", "Untitled Article") if isinstance(article_result, dict) else "Untitled Article",
            "content": article_result.get("content", article_result) if isinstance(article_result, dict) else article_result,
            "transcript_id": int(transcript_id),
            "transcript_content_length": len(transcript_content),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate article: {str(e)}")


@router.post("/article/create/manually")
def generate_article(
    transcript_id: int,
    additional_context: str = "",
    journalist: Journalist = Journalist.AURELIUS_STONE,
    tone: Optional[Tone] = None,
    article_type: Optional[ArticleType] = None,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Generate an article from a transcript without writing to the database (preview)."""
    try:
        db = deps.database
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        transcript_data = db.get_transcript_by_id(transcript_id)
        if not transcript_data:
            raise HTTPException(status_code=404, detail=f"No transcript found with ID {transcript_id}")
        transcript_content = transcript_data[3]
        journalist_classes = {Journalist.AURELIUS_STONE: AureliusStone, Journalist.FR_J1: FRJ1}
        journalist_class = journalist_classes.get(journalist)
        if not journalist_class:
            available_journalists = [j.value for j in Journalist]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journalist '{journalist.value}' not implemented yet. Available journalists: {available_journalists}",
            )
        journalist_instance = journalist_class()
        base_context = journalist_instance.load_context(tone=tone, article_type=article_type)
        full_context = f"{base_context}\n\nTRANSCRIPT CONTENT TO ANALYZE:\n{transcript_content}"
        article_result = journalist_instance.generate_article(full_context, additional_context)
        logger.info(f"Article generated successfully by {journalist_instance.NAME} using transcript ID {transcript_id}")
        return {
            "journalist": journalist_instance.NAME,
            "context": full_context,
            "article_title": article_result.get("title", "Untitled Article") if isinstance(article_result, dict) else "Untitled Article",
            "article_content": article_result.get("content", article_result) if isinstance(article_result, dict) else article_result,
            "transcript_id": transcript_id,
            "transcript_content_length": len(transcript_content),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate article: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate article: {str(e)}",
        )


@router.post("/article/write/{amount_of_articles}")
async def bulk_generate_articles(
    amount_of_articles: int,
    journalist: Journalist = Journalist.FR_J1,
    tone: Tone = Tone.PROFESSIONAL,
    article_type: ArticleType = ArticleType.NEWS,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Bulk generate articles from existing transcripts."""
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
            f"Starting bulk article generation: {amount_of_articles} articles, "
            f"journalist={journalist.value}, tone={tone.value}, type={article_type.value}"
        )
        return await pipeline.run_bulk_write_articles(
            amount_of_articles, journalist, tone, article_type
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk article generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk article generation failed: {str(e)}",
        )


@router.put("/articles/{article_id}")
async def update_article(
    article_id: str,
    request: CreateArticleRequest,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Update an existing article (full update)."""
    try:
        articles_db = deps.articles_db
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )
        article = articles_db[article_id]
        ag = deps.article_generator
        if not ag:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Article generator not available")
        if request.context is not None:
            article["context"] = request.context
        if request.prompt is not None:
            article["prompt"] = request.prompt
        if request.article_type is not None:
            article["article_type"] = request.article_type.value
        if request.tone is not None:
            article["tone"] = request.tone.value
        if request.committee is not None:
            article["committee"] = request.committee
        if any([request.context, request.prompt, request.article_type, request.tone, request.committee]):
            try:
                new_content = ag.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")
        article["updated_at"] = datetime.now().isoformat()
        logger.info(f"Article {article_id} updated successfully")
        return {"message": "Article updated successfully", "article": article}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update article: {str(e)}",
        )


@router.patch("/articles/{article_id}")
async def partial_update_article(
    article_id: str,
    request: PartialUpdateRequest,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Partially update an existing article."""
    try:
        articles_db = deps.articles_db
        if article_id not in articles_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article with ID {article_id} not found",
            )
        article = articles_db[article_id]
        ag = deps.article_generator
        if not ag:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Article generator not available")
        if request.context is not None:
            article["context"] = request.context
        if request.prompt is not None:
            article["prompt"] = request.prompt
        if request.article_type is not None:
            article["article_type"] = request.article_type.value
        if request.tone is not None:
            article["tone"] = request.tone.value
        if request.committee is not None:
            article["committee"] = request.committee
        if any([request.context, request.prompt, request.article_type, request.tone, request.committee]):
            try:
                new_content = ag.write_article(
                    context=article["context"],
                    prompt=article["prompt"],
                    article_type=ArticleType(article["article_type"]),
                    tone=Tone(article["tone"]),
                )
                article["content"] = new_content
            except Exception as e:
                logger.warning(f"Failed to regenerate content: {str(e)}")
        article["updated_at"] = datetime.now().isoformat()
        logger.info(f"Article {article_id} partially updated successfully")
        return {"message": "Article partially updated successfully", "article": article}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to partially update article {article_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to partially update article: {str(e)}",
        )


@router.patch("/article/{article_id}/bullet-points")
def generate_article_bullet_points(
    article_id: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Generate and save bullet points for an existing article."""
    db = deps.database
    if not db:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not available",
        )
    article = db.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found",
        )
    journalist = AureliusStone()
    result = journalist.generate_bullet_points(article["content"])
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )
    success = db.update_article_bullet_points(article_id, result["bullet_points"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update article",
        )
    return {"article_id": article_id, "bullet_points": result["bullet_points"]}


@router.post("/bullet-points/generate/batch/{amount_of_articles}")
def generate_all_bullet_points(
    amount_of_articles: int,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Generate bullet points for all articles that don't have them."""
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
    return pipeline.run_bullet_points_batch(amount_of_articles)
