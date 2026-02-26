"""
Dependency injection container (OOP). Exposes app.state-backed dependencies
as properties for use in route handlers via Depends(AppDependencies).
"""

from typing import Any, Dict, Optional

from fastapi import Request

from app import ArticleGenerator, TranscriptManager
from app.data.create_database import Database
from app.data.journalist_manager import JournalistManager


class AppDependencies:
    """
    Holds request-scoped access to app.state (database, managers, services).
    FastAPI injects one instance per request when using Depends(AppDependencies).
    """

    def __init__(self, request: Request) -> None:
        self._request = request

    @property
    def database(self) -> Optional[Database]:
        return getattr(self._request.app.state, "database", None)

    @property
    def transcript_manager(self) -> Optional[TranscriptManager]:
        return getattr(self._request.app.state, "transcript_manager", None)

    @property
    def article_generator(self) -> Optional[ArticleGenerator]:
        return getattr(self._request.app.state, "article_generator", None)

    @property
    def journalist_manager(self) -> Optional[JournalistManager]:
        return getattr(self._request.app.state, "journalist_manager", None)

    @property
    def articles_db(self) -> Dict[str, Any]:
        return getattr(self._request.app.state, "articles_db", {})

    @property
    def wordpress_sync_service(self) -> Optional[Any]:
        return getattr(self._request.app.state, "wordpress_sync_service", None)

    @property
    def pipeline_service(self) -> Optional[Any]:
        return getattr(self._request.app.state, "pipeline_service", None)

    @property
    def image_service(self) -> Optional[Any]:
        return getattr(self._request.app.state, "image_service", None)
