"""Settings precedence tests."""

from __future__ import annotations

import pytest

from cv_generator import config as cfg


def test_dotenv_overrides_process_env_for_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        cfg,
        "_parse_env_file",
        lambda: {"LLM_PROVIDER": "github", "OPENAI_API_KEY": "sk-from-dotenv"},
    )

    settings = cfg.get_settings()

    assert settings.llm_provider == "github"
    assert settings.openai_api_key is None


def test_ignore_env_file_uses_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("APP_DATA_DIR", "/tmp/e2e-data")

    settings = cfg.get_settings()

    assert settings.llm_provider == "stub"
    assert settings.app_data_dir.as_posix().endswith("e2e-data")
