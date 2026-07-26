"""Logging utilities for QD2.

Provides a unified logging interface using loguru.
"""

import sys
from typing import Optional

from loguru import logger


class Log:
    """Wrapper around loguru for consistent logging across QD2 modules.

    Usage:
        logger = Log("QD.Core").getlogger()
        logger.info("Hello from QD Core")
    """

    def __init__(
        self,
        name: str,
        logger_level: str = "INFO",
        channel_level: Optional[str] = None,
        log_file: Optional[str] = None,
    ):
        self.name = name
        self.logger_level = logger_level
        self.channel_level = channel_level or logger_level
        self.log_file = log_file

    def getlogger(self):
        """Get a configured loguru logger instance."""
        # Remove default handler
        try:
            logger.remove()
        except ValueError:
            pass

        # Add stderr handler
        logger.add(
            sys.stderr,
            level=self.channel_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{extra[name]}</cyan> | "
                   "<level>{message}</level>",
            colorize=True,
        )

        # Add file handler if specified
        if self.log_file:
            logger.add(
                self.log_file,
                level=self.logger_level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[name]} | {message}",
                rotation="10 MB",
                retention="7 days",
            )

        # Bind the logger name
        bound_logger = logger.bind(name=self.name)
        return bound_logger
