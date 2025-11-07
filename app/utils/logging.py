"""
Logging utilities for consistent log formatting across the application.

This module provides standardized logging functions that can be used by any class
to maintain consistent log message formatting throughout the codebase.
"""

import logging
from typing import Optional, Dict, Any


def log_operation(
    logger: logging.Logger, operation: str, details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log operations with consistent formatting.

    Args:
        logger: The logger instance to use for logging
        operation: Name of the operation being performed
        details: Optional dictionary containing additional details about the operation

    Example:
        log_operation(logger, "add_transcript", {"video_id": "abc123", "length": 1500})
    """
    log_message = f"Operation: {operation}"
    if details:
        log_message += f" - Details: {details}"
    logger.info(log_message)


def log_error(
    logger: logging.Logger,
    operation: str,
    error: Exception,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log errors with consistent formatting.

    Args:
        logger: The logger instance to use for logging
        operation: Name of the operation that failed
        error: The exception that occurred
        details: Optional dictionary containing additional details about the operation

    Example:
        log_error(logger, "fetch_transcript", e, {"video_id": "abc123"})
    """
    log_message = f"Operation failed: {operation} - Error: {str(error)}"
    if details:
        log_message += f" - Details: {details}"
    logger.error(log_message)


def log_success(
    logger: logging.Logger, operation: str, details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log successful operations with consistent formatting.

    Args:
        logger: The logger instance to use for logging
        operation: Name of the operation that succeeded
        details: Optional dictionary containing additional details about the operation

    Example:
        log_success(logger, "transcript_cached", {"video_id": "abc123", "transcript_id": 42})
    """
    log_message = f"Success: {operation}"
    if details:
        log_message += f" - Details: {details}"
    logger.info(log_message)


def log_warning(
    logger: logging.Logger,
    operation: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log warnings with consistent formatting.

    Args:
        logger: The logger instance to use for logging
        operation: Name of the operation that generated the warning
        message: Warning message
        details: Optional dictionary containing additional details about the operation

    Example:
        log_warning(logger, "cache_transcript", "Database unavailable", {"video_id": "abc123"})
    """
    log_message = f"Warning in {operation}: {message}"
    if details:
        log_message += f" - Details: {details}"
    logger.warning(log_message)
