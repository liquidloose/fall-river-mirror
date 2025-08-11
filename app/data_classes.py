
from enum import Enum


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op-ed"

class Tone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"

class Committee(str, Enum):
    BOARD_OF_ASSESSORS = "Board of Assessors"
    BOARD_OF_HEALTH = "Board of Health"
    CHARTER_COMMISSION = "Charter Commission"
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
