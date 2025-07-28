
from enum import Enum


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op-ed"

class Tone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
