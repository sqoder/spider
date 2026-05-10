"""
Structured logging configuration using loguru.
Provides console + file logging with rotation.
"""

import sys
from pathlib import Path

from loguru import logger

from youtube_crawler.core.config import get_settings


def setup_logger() -> None:
    """Configure the application logger with console and file outputs."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Console handler with color
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=settings.debug,
    )

    # File handler with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "crawler_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",  # Daily rotation
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,  # Thread-safe
    )

    # Error-specific log file
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention="90 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
    )

    logger.info(f"Logger initialized | env={settings.app_env} | level={settings.log_level}")
