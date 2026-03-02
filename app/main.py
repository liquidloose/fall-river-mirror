# Standard library imports
import logging
import os

from app.data.enum_manager import DatabaseSync

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Third-party imports
from fastapi import APIRouter, FastAPI, HTTPException, Request, Depends, status, Body
from fastapi.responses import JSONResponse, Response
import requests

# Local imports
from app import TranscriptManager, ArticleGenerator
from app.content_department.ai_journalists.aurelius_stone import AureliusStone
from app.content_department.ai_journalists.fr_j1 import FRJ1
from app.data.create_database import Database
from app.data.journalist_manager import JournalistManager
from app.services.image_service import ImageService
from app.services.pipeline_service import PipelineService
from app.services.wordpress_sync_service import WordPressSyncService

# Routers
from app.routers import (
    health,
    transcripts,
    articles,
    images,
    queue,
    pipeline,
    wordpress,
    journalist,
    crawler,
    editor,
)

# testConfigure logging: always console; file only if writable (app.log may be root-owned in Docker)
_handlers = [logging.StreamHandler()]
try:
    _handlers.append(logging.FileHandler("app.log"))
except (OSError, PermissionError):
    pass
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# Initialize database instance at the top level
try:
    database = Database("app/data/fr-mirror")
    logger.info("Database initialized successfully in main.py")
except Exception as e:
    logger.error(f"Failed to initialize database in main.py: {str(e)}")
    database = None

# Initialize database sync and run it
journalist_manager = None
if database:
    db_sync = DatabaseSync(database)
    db_sync.sync_all_enums()
    logger.info(f"Database sync completed: {db_sync}")

    # Initialize journalists as proper entities
    journalist_manager = JournalistManager(database)
    aurelius = AureliusStone()
    frj1 = FRJ1()

    # Create/update Aurelius Stone with bio and description
    journalist_manager.upsert_journalist(
        full_name=aurelius.FULL_NAME,
        first_name=aurelius.FIRST_NAME,
        last_name=aurelius.LAST_NAME,
        bio=aurelius.get_bio(),
        description=aurelius.get_description(),
    )

    # Create/update FRJ1 with bio and description
    journalist_manager.upsert_journalist(
        full_name=frj1.FULL_NAME,
        first_name=frj1.FIRST_NAME,
        last_name=frj1.LAST_NAME,
        bio=frj1.get_bio(),
        description=frj1.get_description(),
    )
    logger.info("Journalist initialization completed")
else:
    journalist_manager = None

# Initialize FastAPI application
app = FastAPI(
    title="Article Generation API",
    description="API for generating articles using AI processing",
    version="1.0.0",
)

logger.info("FastAPI app initialized!")

# Create class instances once at startup
transcript_manager = TranscriptManager(database)
article_generator = ArticleGenerator()

# In-memory storage for demo purposes (replace with actual database operations)
articles_db = {}


# ===== DEPENDENCY INJECTION (for testing override) =====


class AppDeps:
    """Container for app dependencies. Used by route handlers and overridden in tests."""

    def __init__(
        self,
        *,
        database,
        transcript_manager,
        article_generator,
        articles_db,
        journalist_manager=None,
    ):
        self.database = database
        self.transcript_manager = transcript_manager
        self.article_generator = article_generator
        self.articles_db = articles_db
        self.journalist_manager = journalist_manager


def get_app_deps(request: Request) -> AppDeps:
    """FastAPI dependency that returns app deps. Override in tests via app.dependency_overrides."""
    return request.app.state.deps


# Service layer (OOP)
image_service = ImageService()
wordpress_sync_service = WordPressSyncService(database)
pipeline_service = PipelineService(
    database=database,
    transcript_manager=transcript_manager,
    journalist_manager=journalist_manager,
    image_service=image_service,
)

# Attach to app.state for AppDependencies
app.state.database = database
app.state.transcript_manager = transcript_manager
app.state.article_generator = article_generator
app.state.journalist_manager = journalist_manager
app.state.articles_db = articles_db
app.state.image_service = image_service
app.state.wordpress_sync_service = wordpress_sync_service
app.state.pipeline_service = pipeline_service

# For dependency injection (get_app_deps) used by tests
app.state.deps = AppDeps(
    database=database,
    transcript_manager=transcript_manager,
    article_generator=article_generator,
    articles_db=articles_db,
    journalist_manager=journalist_manager,
)

# Include routers
app.include_router(health.router)
app.include_router(transcripts.router)
app.include_router(articles.router)
app.include_router(images.router)
app.include_router(queue.router)
app.include_router(pipeline.router)
app.include_router(wordpress.router)
app.include_router(journalist.router)
app.include_router(crawler.router)
app.include_router(editor.router)
