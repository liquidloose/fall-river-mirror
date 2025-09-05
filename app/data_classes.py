from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op_ed"


class Tone(str, Enum):
    FORMAL = "formal tone"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"


class Journalist(str, Enum):
    AURELIUS_STONE = "Aurelius Stone"


class Committee(str, Enum):
    BOARD_OF_ASSESSORS = "Board of Assessors"
    BOARD_OF_HEALTH = "Board of Health"
    CHARTER_COMMISSION = "Charter Commission"
    CITY_COUNCIL = "City Council"
    COMMUNITY_PRESERVATION_COMMISSION = "Community Preservation Commission"
    CONSERVATION_COMMISSION = "Conservation Commission"
    COUNCIL_ON_AGING = "Council on Aging"
    CULTURAL_COUNCIL = "Cultural Council"
    DISABILITY_COMMISSION = "Disability Commission"
    ELECTION_COMMISSION = "Election Commission"
    HISTORICAL_COMMISSION = "Historical Commission"
    HOUSING_AUTHORITY = "Housing Authority"
    LIBRARY_BOARD_OF_TRUSTEES = "Library Board of Trustees"
    LICENSING_BOARD = "Licensing Board"
    PARK_BOARD = "Park Board"
    PLANNING_BOARD = "Planning Board"
    PORT_AUTHORITY = "Port Authority"
    REDEVELOPMENT_AUTHORITY_BOARD = "Redevelopment Authority Board"
    RETIREMENT_BOARD = "Retirement Board"
    SEWER_COMMISSION = "Sewer Commission"
    SPECIAL_CHARTER_COMMITTEE = "Special Charter Committee"
    TAX_INCREMENT_FINANCE_BOARD = "Tax Increment Finance Board"
    TRAFFIC_COMMISSION = "Traffic Commission"
    WATUPPA_WATER_BOARD = "Watuppa Water Board"
    ZONING_BOARD_OF_APPEALS = "Zoning Board of Appeals"

    @property
    def normalized(self) -> str:
        """Get normalized version for database keys, etc."""
        return self.value.lower().replace(" ", "_").replace("&", "and")


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
    committee: Optional[Committee] = None


class CreateArticleRequest(BaseArticleRequest):
    """Request model for creating new articles. All fields are required."""

    context: str  # Override to make required
    prompt: str  # Override to make required
    article_type: ArticleType  # Override to make required
    tone: Tone  # Override to make required
    committee: Committee  # Override to make required


class UpdateArticleRequest(BaseArticleRequest):
    """Request model for full article updates. All fields are optional."""

    pass  # Inherits all optional fields from base class


class PartialUpdateRequest(BaseArticleRequest):
    """Request model for partial article updates. All fields are optional."""

    pass  # Inherits all optional fields from base class


# Alias for backward compatibility
GenerateArticleRequest = CreateArticleRequest
