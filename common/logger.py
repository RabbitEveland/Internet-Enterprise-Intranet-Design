"""Consistent, rotating application logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(logger_name: str, log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Create an idempotent logger that avoids unbounded on-disk logs."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def close_logger(logger: logging.Logger) -> None:
    """Flush and release handlers so a stopped service does not retain log files."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
