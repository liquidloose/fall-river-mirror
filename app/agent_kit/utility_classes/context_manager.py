import os
import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Parent of utility_classes/ — i.e. app/agent_kit/
_AGENT_KIT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

RoleName = Literal["journalists", "artists", "editors"]
_VALID_ROLES = frozenset(("journalists", "artists", "editors"))


def _role_context_dir(role: RoleName) -> str:
    return os.path.join(_AGENT_KIT_DIR, "agents", role, "context_files")


class ContextManager:
    """Manages context files for AI prompts and instructions."""

    def __init__(self, base_path: str = "app"):
        self.base_path = base_path
        self.context_files_dir = os.path.join(base_path, "context_files")

    def read_context_file(
        self,
        subdir: str,
        filename: str,
        role: Optional[RoleName] = None,
    ) -> str:
        """
        Read content from a context file under ``subdir/filename``.

        When ``role`` is ``journalists``, ``artists``, or ``editors``, reads from
        ``agent_kit/agents/{role}/context_files/{subdir}/{filename}``.

        When ``role`` is ``None``, uses the legacy layout only:
        ``{base_path}/context_files/{subdir}/{filename}`` (default ``base_path`` is
        ``app``, i.e. ``app/context_files``), for backward compatibility with
        :class:`~app.agent_kit.utility_classes.article_generator.ArticleGenerator`.

        Returns stripped UTF-8 text, or ``"default"`` if no candidate file exists or
        on decode/other read errors.
        """
        paths_to_try: list[str] = []
        if role is not None:
            if role in _VALID_ROLES:
                paths_to_try.append(
                    os.path.join(_role_context_dir(role), subdir, filename)
                )
            else:
                logger.warning(
                    "Invalid role %r for read_context_file; returning default",
                    role,
                )
        else:
            paths_to_try.append(
                os.path.join(self.context_files_dir, subdir, filename)
            )

        for filepath in paths_to_try:
            try:
                with open(filepath, "r", encoding="utf-8") as file:
                    content = file.read().strip()
                    logger.info("Successfully loaded context file: %s", filepath)
                    return content
            except FileNotFoundError:
                logger.debug(
                    "Context file not found at %s, trying next candidate", filepath
                )
                continue
            except UnicodeDecodeError as e:
                logger.error(
                    "Failed to decode file %s with UTF-8 encoding: %s", filepath, e
                )
                return "default"
            except Exception as e:
                logger.error("Unexpected error reading file %s: %s", filepath, e)
                return "default"

        logger.error("Context file not found after trying: %s", paths_to_try)
        logger.warning(
            "Returning 'default' for missing file: %s/%s (role=%s)",
            subdir,
            filename,
            role,
        )
        return "default"

    def get_context_path(self) -> str:
        """Get the legacy base path for context files (``base_path/context_files``)."""
        return self.context_files_dir

    def context_file_exists(
        self,
        subdir: str,
        filename: str,
        role: Optional[RoleName] = None,
    ) -> bool:
        """Return True if the file exists for the same resolution rules as :meth:`read_context_file`."""
        if role is not None:
            if role in _VALID_ROLES:
                path = os.path.join(_role_context_dir(role), subdir, filename)
                return os.path.exists(path)
            return False
        return os.path.exists(
            os.path.join(self.context_files_dir, subdir, filename)
        )
