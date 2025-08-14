import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages context files for AI prompts and instructions."""
    
    def __init__(self, base_path: str = "app"):
        self.base_path = base_path
        self.context_files_dir = os.path.join(base_path, "context_files")
    
    def read_context_file(self, subdir: str, filename: str) -> str:
        """
        Read content from a context file in the specified subdirectory.
        
        This method reads text content from context files stored in the context_files/
        directory structure. Context files typically contain prompts, instructions, or
        configuration text that can be used with AI processors.
        
        Args:
            subdir (str): The subdirectory within context_files/ where the file is located.
                          For example: "sentiment", "analysis", "prompts"
            filename (str): The name of the file to read, including extension.
                           For example: "sentiment_analyzer.txt", "prompt_template.txt"
        
        Returns:
            str: The content of the file as a string, with leading/trailing whitespace removed.
                 Returns "default" if the file is not found.
        
        Raises:
            FileNotFoundError: If the specified file does not exist in the expected location.
                              This is caught and logged, then "default" is returned.
        
        Example:
            >>> context_mgr = ContextManager()
            >>> content = context_mgr.read_context_file("sentiment", "analyzer_prompt.txt")
            >>> print(content)
            "Analyze the sentiment of the following text..."
            
            >>> # File structure:
            >>> # app/
            >>> #   context_files/
            >>> #     sentiment/
            >>> #       analyzer_prompt.txt
            >>> #     analysis/
            >>> #       summary_prompt.txt
        
        Note:
            - Files are expected to be in UTF-8 encoding
            - The method automatically strips leading/trailing whitespace
            - If the file is not found, it logs an error and returns "default"
            - This allows for graceful fallback when context files are missing
        """
        try:
            # Construct the full file path
            filepath = os.path.join(self.context_files_dir, subdir, filename)
            
            # Read the file content with UTF-8 encoding
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read().strip()
                logger.info(f"Successfully loaded context file: {filepath}")
                return content
                
        except FileNotFoundError:
            logger.error(f"Context file not found: {filepath}")
            logger.warning(f"Returning 'default' for missing file: {subdir}/{filename}")
            return "default"
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode file {filepath} with UTF-8 encoding: {e}")
            return "default"
        except Exception as e:
            logger.error(f"Unexpected error reading file {filepath}: {e}")
            return "default"
    
    def get_context_path(self) -> str:
        """Get the base path for context files."""
        return self.context_files_dir
    
    def context_file_exists(self, subdir: str, filename: str) -> bool:
        """Check if a context file exists."""
        filepath = os.path.join(self.context_files_dir, subdir, filename)
        return os.path.exists(filepath)
