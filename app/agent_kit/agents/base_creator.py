from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional, Sequence
import os

# Context markdown lives only under agent_kit/agents/{role}/context_files/.
_AGENT_KIT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


class BaseCreator(ABC):
    """
    Base class for all AI creators (journalists, artists, etc.).
    Contains shared functionality and fixed personality traits.

    Implements the singleton pattern — each subclass can only have one instance.

    Subclasses must set ``CONTEXT_FILES_ROLE`` (e.g. ``journalists`` or ``artists``)
    so bios, descriptions, and attribute snippets resolve under
    ``agent_kit/agents/{role}/context_files/``.
    """

    _instance = None

    CONTEXT_FILES_ROLE: ClassVar[Optional[str]] = None

    def __new__(cls):
        """Ensure only one instance of each creator subclass exists."""
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # Fixed identity traits (must be defined by subclasses)
    FIRST_NAME: str
    LAST_NAME: str
    FULL_NAME: str
    NAME: str
    SLANT: str
    STYLE: str

    def _context_search_bases(self) -> Sequence[str]:
        """Single root: ``agent_kit/agents/{role}/context_files`` when role is set."""
        role = type(self).CONTEXT_FILES_ROLE
        if role:
            return (os.path.join(_AGENT_KIT_DIR, "agents", role, "context_files"),)
        return ()

    def get_bio(self) -> str:
        """
        Load and return the creator's biographical information.

        Looks for ``{first_name}_{last_name}_bio.md`` under ``bios/`` in each
        search base (see :meth:`_context_search_bases`).

        Returns:
            str: The bio content, or an error message if the file is not found.
        """
        bio_filename = f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_bio.md"
        last_tried = ""
        for base in self._context_search_bases():
            bio_path = os.path.join(base, "bios", bio_filename)
            last_tried = bio_path
            try:
                with open(bio_path, "r", encoding="utf-8") as file:
                    return file.read().strip()
            except FileNotFoundError:
                continue
            except Exception as e:
                return f"Error loading bio: {str(e)}"
        if not last_tried:
            return (
                f"Bio file not found for {self.FULL_NAME}: "
                "CONTEXT_FILES_ROLE is not set on the creator class"
            )
        return f"Bio file not found for {self.FULL_NAME}: {last_tried}"

    def get_description(self) -> str:
        """
        Load and return the creator's professional description.

        Looks for ``{first_name}_{last_name}_description.md`` under
        ``descriptions/`` in each search base.

        Returns:
            str: The description content, or an error message if the file is not found.
        """
        description_filename = (
            f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_description.md"
        )
        last_tried = ""
        for base in self._context_search_bases():
            description_path = os.path.join(base, "descriptions", description_filename)
            last_tried = description_path
            try:
                with open(description_path, "r", encoding="utf-8") as file:
                    return file.read().strip()
            except FileNotFoundError:
                continue
            except Exception as e:
                return f"Error loading description: {str(e)}"
        if not last_tried:
            return (
                f"Description file not found for {self.FULL_NAME}: "
                "CONTEXT_FILES_ROLE is not set on the creator class"
            )
        return f"Description file not found for {self.FULL_NAME}: {last_tried}"

    def get_base_personality(self) -> Dict[str, Any]:
        """Get the fixed personality traits shared by all creators."""
        return {
            "name": self.NAME,
            "slant": self.SLANT,
            "style": self.STYLE,
        }

    def _load_attribute_context(
        self,
        attribute_type: str,
        attribute_value: str,
        base_path: Optional[str] = None,
    ) -> str:
        """
        Load context markdown for a trait (e.g. tone, slant).

        If ``base_path`` is set, only that directory is used (legacy override).
        Otherwise, tries each root from :meth:`_context_search_bases`.
        """
        file_name = f"{attribute_value.lower().replace(' ', '_')}.md"
        if base_path is not None:
            search_bases: Sequence[str] = (base_path,)
        else:
            search_bases = self._context_search_bases()

        for root in search_bases:
            file_path = os.path.join(root, attribute_type, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    return file.read()
            except FileNotFoundError:
                continue
        return f"Context file not found for {attribute_type}: {attribute_value}"

    @abstractmethod
    def load_context(self, base_path: str = "./context_files") -> str:
        """Load context files for the creator. Implemented by subclasses."""
        pass

    @abstractmethod
    def get_personality(self) -> Dict[str, Any]:
        """Get full personality including subclass-specific traits."""
        pass

    @abstractmethod
    def get_full_profile(self) -> Dict[str, Any]:
        """Return complete profile. Implemented by subclasses."""
        pass
