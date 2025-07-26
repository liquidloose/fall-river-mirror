import os
import textwrap
import logging

logger = logging.getLogger(__name__)


def read_context_file(subdir: str, filename: str) -> str:
    """Read content from a context file"""
    try:
        filepath = os.path.join("app", "context_files", subdir, filename)
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read().strip()
            # Wrap text to specified width
            return content
    except FileNotFoundError:
        logger.error(f"Context file not found: {filepath}")
        return "default"
