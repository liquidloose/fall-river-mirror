from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op_ed"
    CRITICAL = "critical"
    NEWS = "news"
    FEATURE = "feature"
    PROFILE = "profile"
    INVESTIGATIVE = "investigative"
    EDITORIAL = "editorial"


class AIAgent(str, Enum):
    GROK = "Grok"
    WHISPER = "Whisper"


class Tone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    INVESTIGATIVE = "investigative"
    URGENT = "urgent"
    SATIRICAL = "satirical"
    EMPATHETIC = "empathetic"
    ANALYTICAL = "analytical"
    CONVERSATIONAL = "conversational"
    AUTHORITATIVE = "authoritative"
    CRITICAL = "critical"


class Journalist(str, Enum):
    AURELIUS_STONE = "Aurelius Stone"


# Request/Response models
# Using inheritance to avoid code duplication:
# - BaseArticleRequest: Contains all common fields as optional
# - CreateArticleRequest: Overrides fields to make them required for creation
# - UpdateArticleRequest & PartialUpdateRequest: Inherit optional fields for updates
class BaseArticleRequest(BaseModel):
    """Base class for article request models with common attributes."""

    context: Optional[str] = None
    prompt: Optional[str] = None
    article_type: Optional[ArticleType] = None
    tone: Optional[Tone] = None
    committee: Optional[str] = None  # Committee name (required)


class CreateArticleRequest(BaseArticleRequest):
    """Request model for creating new articles. All fields are required."""

    context: str  # Override to make required
    prompt: str  # Override to make required
    article_type: ArticleType  # Override to make required
    tone: Tone  # Override to make required
    committee: str  # Override to make required (Committee name)


class UpdateArticleRequest(BaseArticleRequest):
    """Request model for full article updates. All fields are optional."""

    pass  # Inherits all optional fields from base class


class PartialUpdateRequest(BaseArticleRequest):
    """Request model for partial article updates. All fields are optional."""

    pass  # Inherits all optional fields from base class


# Alias for backward compatibility
GenerateArticleRequest = CreateArticleRequest
