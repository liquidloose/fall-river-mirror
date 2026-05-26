from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op_ed"
    CRITICAL = "critical"
    NEWS = "news"
    SEQUENTIAL_NEWS = "sequential_news"
    FEATURE = "feature"
    PROFILE = "profile"
    INVESTIGATIVE = "investigative"
    EDITORIAL = "editorial"


class Artist(str, Enum):
    SPECTRA_VERITAS = "Spectra Veritas"
    FRA1 = "FRA1"


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
    FR_J1 = "FRJ1"


class Extractor(str, Enum):
    """Agent extractors that turn transcripts into structured anchor envelopes.

    Values are the human-facing ``FULL_NAME`` strings persisted on ``anchors``
    rows. New extractors get a member here and a branch in
    :meth:`~app.services.pipeline_service.PipelineService.run_extract_anchors`.
    """

    GEMMA_NYE = "Gemma Nye"


class ImageModel(str, Enum):
    GPT_IMAGE_1 = "gpt-image-1"
    GROK = "grok-imagine-image"


class TextLLMProvider(str, Enum):
    """Selects backend in :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery`."""

    XAI = "xai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


# Model identifier enums.
#
# Each value is the exact string the provider's API expects as the ``model`` id.
# Agent classes declare a default via a ``MODEL`` ClassVar; callers (e.g. a future
# dropdown in the UI) can override per-instance by passing ``model=`` to
# :class:`LLMTextQuery`. API keys still come from environment variables; only the
# model selection has moved out of ``.env`` into typed enums.
#
# Lists below reflect provider availability verified at slice-build time; refresh
# as providers ship new models or deprecate old ones.


class GeminiModel(str, Enum):
    """Google Gemini model identifiers passed to ``google-genai`` SDK calls."""

    # Preview / frontier (1M context, replaces thinking_budget with thinking_level)
    GEMINI_3_PRO_PREVIEW = "gemini-3-pro-preview"
    GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview"
    # Stable
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"


class XaiModel(str, Enum):
    """xAI Grok model identifiers passed to the xAI SDK."""

    GROK_4_3 = "grok-4.3"
    GROK_4_20_REASONING = "grok-4.20-reasoning"
    GROK_4_20_NON_REASONING = "grok-4.20-non-reasoning"
    GROK_4_20_MULTI_AGENT_0309 = "grok-4.20-multi-agent-0309"
    GROK_3_MINI = "grok-3-mini"


class AnthropicModel(str, Enum):
    """Anthropic Claude model identifiers passed to the Anthropic SDK."""

    CLAUDE_OPUS_4_7 = "claude-opus-4-7"
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"
    # Legacy default kept for backward compat with earlier hardcoded calls.
    CLAUDE_3_5_SONNET_20241022 = "claude-3-5-sonnet-20241022"


# Maps a provider -> the matching model enum class, for runtime validation in
# :class:`LLMTextQuery`. Keep aligned with the enums above.
PROVIDER_TO_MODEL_ENUM: Dict["TextLLMProvider", type] = {
    TextLLMProvider.GEMINI: GeminiModel,
    TextLLMProvider.XAI: XaiModel,
    TextLLMProvider.ANTHROPIC: AnthropicModel,
}


# Default model per provider when the caller does not pass an explicit choice.
# Picked for "best generally-capable model" per provider, not cheapest.
DEFAULT_MODEL_FOR_PROVIDER: Dict["TextLLMProvider", Enum] = {
    TextLLMProvider.GEMINI: GeminiModel.GEMINI_3_PRO_PREVIEW,
    TextLLMProvider.XAI: XaiModel.GROK_4_3,
    TextLLMProvider.ANTHROPIC: AnthropicModel.CLAUDE_SONNET_4_6,
}


def _build_unified_text_model() -> type:
    """Aggregate every text-LLM model value into one flat Enum.

    Built dynamically from the per-provider enums so this can't drift: when a
    provider model is added or removed, the unified enum picks it up
    automatically. Used by API endpoints that want a single dropdown of every
    selectable text model in the OpenAPI / Swagger schema. Recover the
    matching provider + provider-specific enum member with
    :func:`resolve_text_model`.

    Note: relies on the per-provider enums having disjoint NAMEs (e.g.
    ``GEMINI_*``, ``GROK_*``, ``CLAUDE_*``) and disjoint string values.
    """

    members: list[tuple[str, str]] = []
    seen_values: set[str] = set()
    for src in (XaiModel, AnthropicModel, GeminiModel):
        for member in src:
            if member.value in seen_values:
                raise ValueError(
                    f"Duplicate text-model value {member.value!r} across "
                    f"provider enums; cannot build unified TextModel."
                )
            seen_values.add(member.value)
            members.append((member.name, member.value))
    return Enum("TextModel", members, type=str)


TextModel = _build_unified_text_model()


def resolve_text_model(text_model: "TextModel") -> tuple["TextLLMProvider", Enum]:
    """Map a unified :data:`TextModel` member back to its provider + native enum.

    Returns a ``(provider, model_enum_member)`` tuple suitable for passing
    straight into :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery`.
    """

    value = text_model.value
    for provider, model_enum_cls in PROVIDER_TO_MODEL_ENUM.items():
        try:
            return provider, model_enum_cls(value)
        except ValueError:
            continue
    raise ValueError(f"Unknown text model value: {value!r}")


def resolve_gemini_text_model(
    text_model: "TextModel | GeminiModel | None",
    *,
    field_name: str = "text_model",
) -> Optional["GeminiModel"]:
    """Resolve a model input to ``GeminiModel`` for extractor-safe usage.

    Accepts either a unified :data:`TextModel` or a direct :class:`GeminiModel`.
    If a non-Gemini unified model is passed, raises :class:`ValueError` with a
    user-facing message suitable for HTTP 400 responses.
    """
    if text_model is None:
        return None
    if isinstance(text_model, GeminiModel):
        return text_model
    provider, model = resolve_text_model(text_model)
    if provider != TextLLMProvider.GEMINI:
        raise ValueError(
            f"{field_name} must be a Gemini model for extraction; "
            f"got {text_model.value!r} from provider {provider.value!r}."
        )
    return GeminiModel(model.value)


class Committee(str, Enum):
    """Fall River public-meeting committee / board / commission names.

    Values are the canonical, human-facing strings used in transcripts,
    article metadata, and the ``primary_committee`` field of extractor
    envelopes. Keys are normalized ALL_CAPS identifiers derived from the
    value (``&`` -> ``AND``, punctuation stripped, spaces -> underscores).

    The flat structure is intentional: the City Council / School Committee
    nesting that appears in some source lists is presentational only — each
    subcommittee gets its own enum value here.

    Known issues deferred to a follow-up slice:

    * ``HUMAN_SERVICES_HOUSING_YOUTH_AND_ELDER_AFFAIRS`` and
      ``COMMITTEE_ON_HUMAN_SERVICES_HOUSING_YOUTH_ELDER_AND_VETERANS_AFFAIRS``
      are kept as distinct entries; we will collapse them if confirmed to
      refer to the same body.
    * ``LIBRARY_BOARD_OF_TRUSTEES`` was flagged with question marks in the
      source list; included here but pending confirmation that it holds
      public meetings tracked by this system.
    """

    BOARD_OF_ASSESSORS = "Board of Assessors"
    BOARD_OF_HEALTH = "Board of Health"
    CHARTER_COMMISSION = "Charter Commission"
    CITY_COUNCIL = "City Council"
    COMMITTEE_ON_ECONOMIC_DEVELOPMENT_AND_TOURISM = (
        "Committee on Economic Development & Tourism"
    )
    AD_HOC_COMMITTEE_ON_SUBDIVISIONS = "Ad Hoc Committee on Subdivisions"
    HEALTH_AND_ENVIRONMENTAL_AFFAIRS = "Health and Environmental Affairs"
    FINANCE = "Finance"
    PUBLIC_SAFETY = "Public Safety"
    HUMAN_SERVICES_HOUSING_YOUTH_AND_ELDER_AFFAIRS = (
        "Human Services, Housing, Youth & Elder Affairs"
    )
    ORDINANCES_AND_LEGISLATION = "Ordinances & Legislation"
    REAL_ESTATE = "Real Estate"
    REGULATIONS = "Regulations"
    PUBLIC_WORKS_AND_TRANSPORTATION = "Public Works & Transportation"
    TECHNOLOGY_SUBCOMMITTEE = "Technology Subcommittee"
    COMMUNITY_PRESERVATION_AGENCY = "Community Preservation Agency"
    COMMUNITY_PRESERVATION_COMMISSION = "Community Preservation Commission"
    COMMUNITY_DEVELOPMENT_AGENCY = "Community Development Agency"
    CONSERVATION_COMMISSION = "Conservation Commission"
    COUNCIL_ON_AGING = "Council on Aging"
    CULTURAL_COUNCIL = "Cultural Council"
    DISABILITY_COMMISSION = "Disability Commission"
    ELECTION_COMMISSION = "Election Commission"
    HISTORICAL_COMMISSION = "Historical Commission"
    HOUSING_AUTHORITY = "Housing Authority"
    COMMITTEE_ON_HUMAN_SERVICES_HOUSING_YOUTH_ELDER_AND_VETERANS_AFFAIRS = (
        "Committee on Human Services, Housing, Youth, Elder & Veterans Affairs"
    )
    LIBRARY_BOARD_OF_TRUSTEES = "Library Board of Trustees"
    LICENSING_BOARD = "Licensing Board"
    MUNICIPAL_BID_OPENING = "Municipal Bid Opening"
    PARK_BOARD = "Park Board"
    PLANNING_BOARD = "Planning Board"
    PORT_AUTHORITY = "Port Authority"
    REDEVELOPMENT_AUTHORITY_BOARD = "Redevelopment Authority Board"
    RETIREMENT_BOARD = "Retirement Board"
    SCHOOL_COMMITTEE = "School Committee"
    FACILITIES_AND_OPERATIONS_SUBCOMMITTEE = "Facilities & Operations Subcommittee"
    GRIEVANCE_SUBCOMMITTEE = "Grievance Subcommittee"
    PARENT_AND_COMMUNITY_OUTREACH_SUBCOMMITTEE = (
        "Parent & Community Outreach Subcommittee"
    )
    FINANCE_SUB_COMMITTEE = "Finance Sub Committee"
    INSTRUCTIONAL_SUBCOMMITTEE = "Instructional Subcommittee"
    POLICY_SUBCOMMITTEE = "Policy Subcommittee"
    PUBLIC_HEARING = "Public Hearing"
    REGULAR_MEETING = "Regular Meeting"
    SPECIAL_ED_ALTERNATIVE_ED_AND_EARLY_CHILDHOOD_SUBCOMMITTEE = (
        "Special Ed / Alternative Ed and Early Childhood Subcommittee"
    )
    EVALUATION_SUB_COMMITTEE = "Evaluation Sub Committee"
    SEWER_BOARD = "Sewer Board"
    SPECIAL_CHARTER_COMMITTEE = "Special Charter Committee"
    TAX_INCREMENT_FINANCE_BOARD = "Tax Increment Finance Board"
    TRAFFIC_COMMISSION = "Traffic Commission"
    TICKET_AMNESTY = "Ticket Amnesty"
    WATUPPA_WATER_BOARD = "Watuppa Water Board"
    ZONING_BOARD_OF_APPEALS = "Zoning Board of Appeals"


def committee_list_for_prompt() -> str:
    """Render the :class:`Committee` enum as a markdown bullet list.

    Used by extractors that need the LLM to classify a transcript against the
    canonical committee list. Returns one ``- {value}`` line per committee,
    in declaration order, with no trailing newline.
    """
    return "\n".join(f"- {c.value}" for c in Committee)


class RollCallType(str, Enum):
    """Distinguishes the two kinds of roll call that show up in municipal meetings.

    An anchor's ``roll_call_type`` is mutually exclusive: a single moment in the
    transcript is either an attendance check, a voting roll call, or neither —
    never two at once. ``VOTING`` implies the anchor's ``has_official_vote``
    is also ``True``; ``ATTENDANCE`` is independent of voting.
    """

    NONE = "none"
    """No roll call at this anchor (the common case for ordinary discussion/decision anchors)."""

    ATTENDANCE = "attendance"
    """Clerk-led roll call — members called by name to record present/absent,
    typically at meeting start or after a recess. Not chair introductions or
    a bare quorum statement. Independent of any vote."""

    VOTING = "voting"
    """Formal decision resolved by a recorded named-member roll-call vote
    (each member's yea/nay/abstain individually recorded). Implies ``has_official_vote=True``."""


class PipelineQueueMode(str, Enum):
    """Whether to build the queue from the channel (use Whisper when needed) or only process existing queue (skip Whisper path)."""

    USE_WHISPER = "Use Whisper"
    """Build queue from channel, then fetch transcripts; use Whisper for videos without captions (default)."""

    SKIP_WHISPER = "Skip Whisper"
    """Skip queue build; only fetch transcripts for videos already in the queue."""


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
