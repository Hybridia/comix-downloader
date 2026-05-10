"""
Logging utility - disabled by default, can be enabled via settings.
"""

import logging
import sys
from typing import Optional

# Global flag to track if logging is enabled
_logging_enabled = False
_handlers_added = False


def setup_logging(enable: bool = False, level: int = logging.DEBUG) -> None:
    """
    Setup logging configuration.
    
    Args:
        enable: Whether to enable logging (disabled by default)
        level: Logging level (DEBUG by default when enabled)
    """
    global _logging_enabled, _handlers_added
    _logging_enabled = enable
    
    root_logger = logging.getLogger("comix")
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    if enable and not _handlers_added:
        root_logger.setLevel(level)
        
        # Console handler with formatting
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        _handlers_added = True
    else:
        # Set to a very high level to effectively disable
        root_logger.setLevel(logging.CRITICAL + 1)
        _handlers_added = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    if name.startswith("src."):
        name = name.replace("src.", "comix.", 1)
    elif not name.startswith("comix"):
        name = f"comix.{name}"
    
    return logging.getLogger(name)


def is_logging_enabled() -> bool:
    """Check if logging is currently enabled."""
    return _logging_enabled
