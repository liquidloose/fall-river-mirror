from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..data.data_classes import Tone, ArticleType


class BaseJournalist(ABC):
    NAME: str
    DEFAULT_TONE: Tone
    DEFAULT_ARTICLE_TYPE: ArticleType
    SLANT: str
    STYLE: str

    @classmethod
    def get_personality(
        cls, tone: Optional[Tone] = None, article_type: Optional[ArticleType] = None
    ) -> Dict[str, Any]:
        """
        Get personality traits, allowing for mutable tone and article_type.
        If not provided, use default values.
        """
        selected_tone = tone if tone else cls.DEFAULT_TONE
        selected_article_type = (
            article_type if article_type else cls.DEFAULT_ARTICLE_TYPE
        )
        return {
            "name": cls.NAME,
            "tone": selected_tone.value,
            "article_type": selected_article_type.value,
            "slant": cls.SLANT,
            "style": cls.STYLE,
        }

    @classmethod
    @abstractmethod
    def load_context(
        cls,
        base_path: str = "./context_files",
        tone: Optional[Tone] = None,
        article_type: Optional[ArticleType] = None,
    ) -> str:
        pass

    @classmethod
    @abstractmethod
    def generate_article(
        cls,
        context: str,
        user_content: str,
        tone: Optional[Tone] = None,
        article_type: Optional[ArticleType] = None,
    ) -> str:
        pass
