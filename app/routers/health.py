"""Health check router."""

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends

from app.dependencies import AppDependencies

router = APIRouter(tags=["health"])


@router.get("/")
def health_check(deps: AppDependencies = Depends(AppDependencies)) -> Dict[str, str]:
    """
    Health check endpoint to verify the server is running.

    Returns:
        dict: Status message indicating server is operational
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Health check endpoint called!")
    db = deps.database
    db_status = "connected" if db and db.is_connected else "disconnected"
    return {
        "status": "ok",
        "message": "Server is running",
        "database": db_status,
        "timestamp": datetime.now().isoformat(),
    }
