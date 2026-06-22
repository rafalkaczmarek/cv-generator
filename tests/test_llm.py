"""Tests for the LLM client factory error paths."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cv_generator.services import llm


def test_get_llm_rejects_placeholder_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        llm_provider="openai",
        openai_api_key="sk-...",
        openai_model="gpt-4o-mini",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="placeholder"):
        llm.get_llm()


def test_get_llm_requires_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        llm_provider="openai",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.get_llm()


def test_get_llm_requires_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        llm_provider="github",
        github_token=None,
        github_model="openai/gpt-4.1-mini",
        github_base_url="https://models.github.ai/inference",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        llm.get_llm()


def test_get_llm_requires_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        llm_provider="anthropic",
        anthropic_api_key=None,
        anthropic_model="claude-3-5-sonnet-latest",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.get_llm()


def test_get_llm_rejects_unsupported_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(llm_provider="unknown")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="Unsupported LLM provider"):
        llm.get_llm()
