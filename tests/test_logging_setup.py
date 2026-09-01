"""Tests for package logging setup and Settings log file resolution."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cv_generator import config as cfg
from cv_generator.logging_setup import (
    PACKAGE_LOGGER_NAME,
    configure_logging,
    reset_logging,
)


def _flush_package_logger() -> None:
    for handler in logging.getLogger(PACKAGE_LOGGER_NAME).handlers:
        handler.flush()


def test_resolved_log_file_defaults_under_app_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))

    settings = cfg.get_settings()

    assert settings.resolved_log_file() == data_dir / "cv-generator.log"


def test_resolved_log_file_off_disables_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_FILE", "off")

    settings = cfg.get_settings()

    assert settings.resolved_log_file() is None


def test_resolved_log_file_custom_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "logs" / "app.log"
    monkeypatch.setenv("LOG_FILE", str(custom))

    settings = cfg.get_settings()

    assert settings.resolved_log_file() == custom


def test_invalid_log_level_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    settings = cfg.get_settings()

    assert settings.log_level == "INFO"


def test_configure_logging_writes_rotating_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_logging()

    configure_logging(cfg.get_settings(), force=True)
    logging.getLogger("cv_generator.services.example").info("hello-from-test")
    _flush_package_logger()

    log_path = data_dir / "cv-generator.log"
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "hello-from-test" in text
    assert "cv_generator.services.example" in text
    assert "Logging configured" in text


def test_configure_logging_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    reset_logging()
    settings = cfg.get_settings()

    first = configure_logging(settings, force=True)
    second = configure_logging(settings)

    assert first is second
    assert len(first.handlers) == len(second.handlers) == 2


def test_configure_logging_off_uses_stderr_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_FILE", "off")
    reset_logging()

    logger = configure_logging(cfg.get_settings(), force=True)

    assert len(logger.handlers) == 1
    assert logger.handlers[0].name == "cv_generator.stderr"
    assert not (tmp_path / "data" / "cv-generator.log").exists()


def test_configure_logging_quiet_noisy_loggers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    reset_logging()

    configure_logging(cfg.get_settings(), force=True)

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("langchain").level == logging.WARNING
