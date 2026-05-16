"""
Fall River **official names** — load canonical spellings from markdown for prompts and tooling.

**Source file**

Default path is ``agent_kit/agents/editors/context_files/official_names.md`` (resolved from
this module’s location). That keeps the roster next to other editor prompt assets. Override
via :class:`OfficialNamesLoader` ``path`` for tests or alternate layouts.

**Markdown shape** (informal contract)

- Optional title/intro **before** the first ``##`` section — not parsed as names; use plain
  paragraphs; avoid ``-`` / ``*`` list lines there if they would be mistaken for names.
- One ``## Section title`` per board/role, then bullet list items: ``- Name`` or ``* Name``.
- :func:`get_canonical_names` collects **only** those list lines **after** the first ``##``
  (see :func:`_list_items_after_first_heading`).
- :func:`get_guideline_text` returns the **entire** file as UTF-8 text (stripped) for LLM
  system prompts (e.g. :class:`~app.agent_kit.agents.journalists.fr_j1.FRJ1`,
  :class:`~app.agent_kit.agents.editors.editor_agent.EditorAgent`).

**Caching**

Each :class:`OfficialNamesLoader` instance reads the file at most once per process for raw
text and once for the derived name list. Module-level :func:`get_guideline_text` /
:func:`get_canonical_names` share a single default loader instance.
"""
import os
import re
from typing import List

_DEFAULT_MD_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "agents",
        "editors",
        "context_files",
        "official_names.md",
    )
)


def _list_items_after_first_heading(text: str) -> List[str]:
    """
    Parse list items that belong to ``##`` sections.

    Everything before the first line starting with ``##`` is ignored (intro / title).
    For each subsequent line, rows matching ``- item`` or ``* item`` contribute
    ``item`` to the result, in document order, across all sections.
    """
    names: List[str] = []
    seen_heading = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            seen_heading = True
            continue
        if not seen_heading:
            continue
        m = re.match(r"^[-*]\s+(.+)$", stripped)
        if m:
            names.append(m.group(1).strip())
    return names


class OfficialNamesLoader:
    """
    Read ``official_names.md`` once per instance and expose prompt text plus a flat name list.

    Callers typically use the module helpers :func:`get_guideline_text` and
    :func:`get_canonical_names` instead of instantiating this class directly.
    """

    def __init__(self, path: str | None = None) -> None:
        """
        Args:
            path: Filesystem path to the markdown file. Defaults to ``_DEFAULT_MD_PATH``
                next to ``agents/editors/context_files/`` in this package tree.
        """
        self._path = path or _DEFAULT_MD_PATH
        self._text: str | None = None
        self._names: List[str] | None = None

    def _load_text(self) -> str:
        """Read and cache the file contents (UTF-8)."""
        if self._text is None:
            with open(self._path, encoding="utf-8") as f:
                self._text = f.read()
        return self._text

    def get_canonical_names(self) -> List[str]:
        """
        Return every bullet name from ``##`` sections, in order, as separate strings.

        Suitable for spelling / validation logic that needs a flat iterable, not full prose.
        """
        if self._names is None:
            self._names = _list_items_after_first_heading(self._load_text())
        return list(self._names)

    def get_guideline_text(self) -> str:
        """Return the full markdown document, stripped, for embedding in LLM prompts."""
        return self._load_text().strip()


# Module-level default loader (lazy singleton) for :func:`get_guideline_text` /
# :func:`get_canonical_names`.
_loader: OfficialNamesLoader | None = None


def _get_loader() -> OfficialNamesLoader:
    """Return the shared :class:`OfficialNamesLoader` using the default markdown path."""
    global _loader
    if _loader is None:
        _loader = OfficialNamesLoader()
    return _loader


def get_canonical_names() -> List[str]:
    """Same as :meth:`OfficialNamesLoader.get_canonical_names` on the default loader."""
    return _get_loader().get_canonical_names()


def get_guideline_text() -> str:
    """Same as :meth:`OfficialNamesLoader.get_guideline_text` on the default loader."""
    return _get_loader().get_guideline_text()
