"""
Load Fall River official names from the canonical data file.
Used by FRJ1 for guidelines and by the spelling-check endpoint.
"""
import json
import os
from typing import List

# Path to official_names.json relative to this module
DEFAULT_JSON_PATH = os.path.join(os.path.dirname(__file__), "official_names.json")


class OfficialNamesLoader:
    """
    Loads and caches the official names data file.
    Exposes canonical names list and guideline text for FRJ1.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or DEFAULT_JSON_PATH
        self._data: dict | None = None

    def _load_data(self) -> dict:
        if self._data is None:
            with open(self._path, encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def get_canonical_names(self) -> List[str]:
        """Return a flat list of all canonical official name strings for spelling check."""
        data = self._load_data()
        names: List[str] = []
        for section in data.get("sections", []):
            names.extend(section.get("names", []))
        return names

    def get_guideline_text(self) -> str:
        """Return the official-names bullet text for FRJ1 get_guidelines()."""
        data = self._load_data()
        intro = data.get("intro", "")
        lines = [f"- {intro}"]
        for section in data.get("sections", []):
            label = section.get("label", "")
            names = section.get("names", [])
            if label and names:
                names_str = ", ".join(names)
                lines.append(f"- {label}: {names_str}")
        return "\n".join(lines)


# Default instance for backward-compatible module-level access
_loader: OfficialNamesLoader | None = None


def _get_loader() -> OfficialNamesLoader:
    global _loader
    if _loader is None:
        _loader = OfficialNamesLoader()
    return _loader


def get_canonical_names() -> List[str]:
    """Return a flat list of all canonical official name strings."""
    return _get_loader().get_canonical_names()


def get_guideline_text() -> str:
    """Return the official-names bullet text for FRJ1 get_guidelines()."""
    return _get_loader().get_guideline_text()
