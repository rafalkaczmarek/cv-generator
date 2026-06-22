"""Settings precedence tests."""

from __future__ import annotations

import pytest

from cv_generator import config as cfg


def test_dotenv_overrides_process_env_for_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = cfg.get_settings()

    assert settings.llm_provider == "github"
    assert settings.openai_api_key is None
