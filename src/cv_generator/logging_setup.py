"""Stdlib logging for the ``cv_generator`` package.

Configures a package-level logger (not the root logger) with stderr output and
a rotating file under ``APP_DATA_DIR`` by default. Safe to call on every
Streamlit rerun — existing handlers are reused and only the level is updated.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv_generator.config import Settings

PACKAGE_LOGGER_NAME = "cv_generator"
_STDERR_HANDLER_NAME = "cv_generator.stderr"
_FILE_HANDLER_NAME = "cv_generator.file"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 1_048_576
_BACKUP_COUNT = 5

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "openai",
    "anthropic",
    "google",
    "googleapiclient",
    "google_auth_httplib2",
    "langchain",
    "langchain_core",
    "langgraph",
    "watchdog",
    "git",
)


def reset_logging() -> None:
    """Remove handlers from the package logger. Used in tests to release files."""
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def configure_logging(settings: Settings | None = None, *, force: bool = False) -> logging.Logger:
    """Attach stderr + optional file handlers to the ``cv_generator`` logger."""
    if settings is None:
        from cv_generator.config import get_settings

        settings = get_settings()

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)

    if logger.handlers and not force:
        _apply_level(logger, level)
        _quiet_noisy_loggers()
        return logger

    reset_logging()
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.name = _STDERR_HANDLER_NAME
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_file = settings.resolved_log_file()
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.name = _FILE_HANDLER_NAME
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("Could not open log file %s — stderr only", log_file)

    _quiet_noisy_loggers()
    logger.info(
        "Logging configured level=%s file=%s",
        settings.log_level,
        str(log_file) if log_file is not None else "off",
    )
    return logger


def _apply_level(logger: logging.Logger, level: int) -> None:
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


def _quiet_noisy_loggers() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = ["PACKAGE_LOGGER_NAME", "configure_logging", "reset_logging"]
