from app.data.enum_classes import Tone, ArticleType
from app.content_department.ai_journalists.base_journalist import BaseJournalist


class FRJ1(BaseJournalist):
    """
    FRJ1 - An AI journalist personality.
    Inherits shared functionality from BaseJournalist and BaseCreator.
    """

    # Fixed identity traits
    FIRST_NAME = "FR"
    LAST_NAME = "J1"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "unbiased"
    STYLE = "journalistic"

    # Journalist-specific defaults
    DEFAULT_TONE = Tone.ANALYTICAL
    DEFAULT_ARTICLE_TYPE = ArticleType.OP_ED

    def get_guidelines(self) -> str:
        """Return FRJ1's specific article guidelines."""
        guidelines = [
            "- Internal Breakdown: Analyze the transcript to identify major agenda items and key speakers for each topic.",
            "- Tracking Outcomes: Note specific results such as votes, items being tabled, or delays.",
            "- Identifying Conflict: Pinpoint moments of significant disagreement or heated exchanges.",
            "- Content Planning: Use this breakdown to ensure a detailed 500-800 word count without resorting to repetitive filler.",
            "- Factual Reporting: Provide a comprehensive account of all discussions and decisions.",
            "- Journalistic Formatting: Include a clear headline, an informative lead paragraph, and a detailed body.",
            "- Professional Boundaries: Start the report directly; do not introduce yourself.",
            "- Don't introduce yourself in the article.",
            "- Write a comprehensive, factual account of what was discussed and decided in the meeting",
            "- Use proper journalistic formatting with headline, lead paragraph, and body",
            "- Maintain the specified tone and style throughout",
            "- Report what happened without expressing opinions about whether decisions are good or bad",
            "- Provide factual context and background for decisions and discussions",
            "- Explain what was decided, who said what, and what the outcomes were",
            "- Focus on the key points, decisions, and discussions from the transcript",
            "- If there are any emergencies, mention them in the article and explain why they are scheduled and when they are happening.",
            "- Explain what issues were discussed and note public participation to show local engagement",
            "- Write at least 500-800 words with substantial detail about what transpired",
            "- Include multiple paragraphs with thorough coverage of the meeting's content",
            "- Present information objectively without bias or commentary on the merits of decisions",
            "- Do not praise or criticize the councilor members or citizens",
            "- Do not mention procedural details like roll call, reading of decorum rules, agenda approvals, or other routine administrative housekeeping",
            "- Focus exclusively on substantive content, decisions, debates, and outcomes",
            "- Do not use generic, repetitive openings like 'Ever wonder how...' or 'Let's break down...' - start directly with the specific content and decisions from this meeting",
            "- Write as if this is one of many articles about the same city, so avoid explaining basic concepts about how city government works",
        ]
        return "\n".join(guidelines)
