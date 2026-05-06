#!/usr/bin/env python3
"""
VoiceMap Logging Module
Centralized logging configuration for VoiceMap analysis
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "voicemap",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Set up a logger with both console and file output.
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional log file path
        console_output: Whether to output to console
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # ALSO configure the root logger so loggers from sibling modules
    # (analyzer / plotter / metrics — each does logger = get_logger(__name__))
    # propagate to the same console output. Without this, INFO logs from
    # those modules silently disappear in the CLI.
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler — attach to root so everything propagates here
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return logger


def get_logger(name: str = "voicemap") -> logging.Logger:
    """
    Get an existing logger or create a new one.
    
    Args:
        name: Logger name
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
