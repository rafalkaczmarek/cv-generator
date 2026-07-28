"""Tests for Streamlit UI helpers (no widget rendering)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cv_generator.ui import llm as ui_llm
from cv_generator.ui import state as ui_state


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            SimpleNamespace(llm_provider="openai", openai_model="gpt-4o-mini"),
            "OpenAI (gpt-4o-mini)",
        ),
        (
            SimpleNamespace(llm_provider="github", github_model="openai/gpt-4.1-mini"),
            "GitHub Models (openai/gpt-4.1-mini)",
        ),
        (
            SimpleNamespace(llm_provider="anthropic", anthropic_model="claude-3-5-sonnet"),
            "Anthropic (claude-3-5-sonnet)",
        ),
        (SimpleNamespace(llm_provider="stub"), "stub"),
    ],
)
def test_llm_provider_label(settings: SimpleNamespace, expected: str) -> None:
    assert ui_llm.llm_provider_label(settings) == expected


def test_format_llm_error_invalid_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ui_llm,
        "llm_provider_label",
        lambda _settings: "GitHub Models (openai/gpt-4.1-mini)",
    )
    monkeypatch.setattr(
        "cv_generator.config.get_settings",
        lambda: SimpleNamespace(llm_provider="github"),
    )

    message = ui_llm.format_llm_error(RuntimeError("invalid_api_key: Incorrect API key"))
    assert "GitHub Models" in message
    assert "OPENAI_API_KEY" in message
    assert "invalid_api_key" in message


def test_format_llm_error_github_no_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cv_generator.config.get_settings",
        lambda: SimpleNamespace(
            llm_provider="github",
            github_model="openai/gpt-4.1-mini",
        ),
    )

    message = ui_llm.format_llm_error(RuntimeError("no_access for model xyz"))
    assert "models:read" in message
    assert "no_access" in message


def test_format_llm_error_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cv_generator.config.get_settings",
        lambda: SimpleNamespace(llm_provider="stub"),
    )

    message = ui_llm.format_llm_error(RuntimeError("timeout talking to provider"))
    assert message == "timeout talking to provider"


def test_ensure_entry_id_assigns_missing_id() -> None:
    entry: dict = {"name": "x"}
    entry_id = ui_state.ensure_entry_id(entry)
    assert entry_id
    assert entry["_id"] == entry_id


def test_ensure_entry_id_keeps_existing() -> None:
    entry = {"_id": "fixed-id", "name": "x"}
    assert ui_state.ensure_entry_id(entry) == "fixed-id"
    assert entry["_id"] == "fixed-id"


def test_strip_entry_id_removes_only_id() -> None:
    assert ui_state.strip_entry_id({"_id": "a", "name": "Ada", "role": "dev"}) == {
        "name": "Ada",
        "role": "dev",
    }


def test_with_entry_ids_fills_gaps() -> None:
    items = [{"name": "a"}, {"_id": "keep", "name": "b"}]
    result = ui_state.with_entry_ids(items)
    assert result is items
    assert items[0]["_id"]
    assert items[1]["_id"] == "keep"


class _FakeSessionState(dict):
    """Minimal stand-in for Streamlit session_state (dict + attribute access)."""

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


def test_delete_buffer_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSessionState(
        {
            "buf": [
                {"_id": "keep", "name": "a"},
                {"_id": "drop", "name": "b"},
            ]
        }
    )
    monkeypatch.setattr(ui_state.st, "session_state", session)

    ui_state.delete_buffer_entry("buf", "drop")
    assert session["buf"] == [{"_id": "keep", "name": "a"}]


def test_ss_get_and_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSessionState()
    monkeypatch.setattr(ui_state.st, "session_state", session)

    assert ui_state.ss_get("missing") is None
    assert ui_state.ss_get("missing", "fallback") == "fallback"

    store = ui_state.storage()
    assert session["storage"] is store
    assert ui_state.storage() is store
