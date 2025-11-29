# Main app package
from .data.transcript_manager import TranscriptManager
from .writing_department.writing_tools.context_manager import ContextManager
from .writing_department.writing_tools.article_generator import ArticleGenerator

__all__ = [
    # Core classes
    "TranscriptManager",
    "ContextManager",
    "ArticleGenerator",
    "YouTubeCrawler",
]
