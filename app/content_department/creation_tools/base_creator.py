from abc import ABC, abstractmethod
from typing import Dict, Any
import os


class BaseCreator(ABC):
    """
    Base class for all AI creators (journalists, artists, etc.).
    Contains shared functionality and fixed personality traits.

    Implements the singleton pattern — each subclass can only have one instance.
    """

    _instance = None

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

    def get_bio(self) -> str:
        """
        Load and return the creator's biographical information.

        Looks for a text file in the 'context_files/bios/' directory with a filename
        matching the creator's name in the format: {first_name}_{last_name}_bio.txt

        Example:
            For a creator with FIRST_NAME="John" and LAST_NAME="Smith",
            this method loads: context_files/bios/john_smith_bio.txt

        Returns:
            str: The bio content, or an error message if the file is not found.
        """
        bio_filename = f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_bio.txt"
        context_files_path = os.path.join(
            os.path.dirname(__file__), "context_files", "bios"
        )
        bio_path = os.path.join(context_files_path, bio_filename)
        try:
            with open(bio_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            return f"Bio file not found for {self.FULL_NAME}: {bio_path}"
        except Exception as e:
            return f"Error loading bio: {str(e)}"

    def get_description(self) -> str:
        """
        Load and return the creator's professional description.

        Looks for a text file in the 'context_files/descriptions/' directory with a
        filename matching the creator's name in the format:
        {first_name}_{last_name}_description.txt

        Example:
            For a creator with FIRST_NAME="Jane" and LAST_NAME="Doe",
            this method loads: context_files/descriptions/jane_doe_description.txt

        Returns:
            str: The description content, or an error message if the file is not found.
        """
        description_filename = (
            f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_description.txt"
        )
        context_files_path = os.path.join(
            os.path.dirname(__file__), "context_files", "descriptions"
        )
        description_path = os.path.join(context_files_path, description_filename)
        try:
            with open(description_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            return (
                f"Description file not found for {self.FULL_NAME}: {description_path}"
            )
        except Exception as e:
            return f"Error loading description: {str(e)}"

    def get_base_personality(self) -> Dict[str, Any]:
        """Get the fixed personality traits shared by all creators."""
        return {
            "name": self.NAME,
            "slant": self.SLANT,
            "style": self.STYLE,
        }

    def _load_attribute_context(
        self, base_path: str, attribute_type: str, attribute_value: str
    ) -> str:
        """Helper method to load context content for a specific attribute."""
        file_name = f"{attribute_value.lower().replace(' ', '_')}.txt"
        file_path = os.path.join(base_path, attribute_type, file_name)
        try:
            with open(file_path, "r") as file:
                return file.read()
        except FileNotFoundError:
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
