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
