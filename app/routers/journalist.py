"""Journalist profile endpoint."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import AppDependencies
from app.data.enum_classes import Journalist
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_journalists.fr_j1 import FRJ1

router = APIRouter(tags=["journalist"])
logger = logging.getLogger(__name__)


@router.get("/journalist/{journalist_name}")
def get_journalist_profile(
    journalist_name: Journalist,
    deps: AppDependencies = Depends(AppDependencies),
) -> Dict[str, Any]:
    """Get complete profile information for a specific journalist."""
    try:
        journalist_classes = {
            Journalist.AURELIUS_STONE: AureliusStone,
            Journalist.FR_J1: FRJ1,
        }
        journalist_class = journalist_classes.get(journalist_name)
        if not journalist_class:
            available_journalists = [j.value for j in Journalist]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journalist '{journalist_name.value}' not found. Available journalists: {available_journalists}",
            )
        journalist = journalist_class()
        profile = journalist.get_full_profile()
        profile.update({
            "default_tone": journalist.DEFAULT_TONE.value,
            "default_article_type": journalist.DEFAULT_ARTICLE_TYPE.value,
            "slant": journalist.SLANT,
            "style": journalist.STYLE,
            "first_name": journalist.FIRST_NAME,
            "last_name": journalist.LAST_NAME,
            "full_name": journalist.FULL_NAME,
        })
        try:
            slant = journalist._load_attribute_context(
                "./app/context_files", "slant", journalist.SLANT
            )
            style = journalist._load_attribute_context(
                "./app/context_files", "style", journalist.STYLE
            )
            tone = journalist._load_attribute_context(
                "./app/context_files", "tone", journalist.DEFAULT_TONE.value
            )
            profile.update({"slant": slant, "style": style, "tone": tone})
        except Exception as e:
            logger.warning(f"Could not load context files: {str(e)}")
            profile.update({
                "slant": "Context file not available",
                "style": "Context file not available",
                "tone": "Context file not available",
            })
        logger.info(f"Retrieved complete profile for {journalist.FULL_NAME}")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve journalist profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve journalist profile: {str(e)}",
        )
