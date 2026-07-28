"""LLM sidebar and user-facing error formatting."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st

# …/src/cv_generator/ui/llm.py → parents[3] is the project root.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def llm_provider_label(settings: Any) -> str:
    if settings.llm_provider == "openai":
        return f"OpenAI ({settings.openai_model})"
    if settings.llm_provider == "github":
        return f"GitHub Models ({settings.github_model})"
    if settings.llm_provider == "anthropic":
        return f"Anthropic ({settings.anthropic_model})"
    return settings.llm_provider


def format_llm_error(exc: Exception) -> str:
    from cv_generator.config import get_settings

    settings = get_settings()
    provider = llm_provider_label(settings)
    message = str(exc)
    if "invalid_api_key" in message or "Incorrect API key" in message:
        return (
            f"Aktywny provider: **{provider}**.\n\n"
            "Wygląda na to, że zapytanie trafiło do OpenAI z placeholderem `sk-...`. "
            "Najczęstsze przyczyny:\n"
            "- w `.env` zostawiono `OPENAI_API_KEY=sk-...` przy `LLM_PROVIDER=github` "
            "(usuń tę linię lub zostaw pustą)\n"
            "- terminal/IDE wstrzykuje `OPENAI_API_KEY` do środowiska procesu\n\n"
            "Sprawdź plik `.env` w katalogu projektu:\n"
            "- **GitHub Models**: `LLM_PROVIDER=github` i `GITHUB_TOKEN` z `models:read`\n"
            "- **OpenAI**: `LLM_PROVIDER=openai` i prawdziwy `OPENAI_API_KEY`\n\n"
            f"Szczegóły: {message}"
        )
    if "no_access" in message and "model" in message.lower():
        return (
            "Brak dostępu do modelu na GitHub Models. Token musi mieć uprawnienie **models:read** "
            "(fine-grained PAT → Permissions → Models → Read). "
            "Możesz też sprawdzić dostęp w https://github.com/marketplace/models.\n\n"
            f"Szczegóły: {message}"
        )
    return message


def render_llm_sidebar() -> None:
    from cv_generator.config import get_settings

    settings = get_settings()
    with st.sidebar:
        st.subheader("LLM")
        st.caption(llm_provider_label(settings))
        st.caption(f"Konfiguracja: `{_ENV_FILE}`")
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider and env_provider != settings.llm_provider:
            st.warning(
                f"Środowisko procesu ma `LLM_PROVIDER={env_provider}`, "
                f"ale używany jest `{settings.llm_provider}` z `.env`."
            )
        if settings.llm_provider != "openai" and os.environ.get("OPENAI_API_KEY"):
            st.warning("Wykryto OPENAI_API_KEY w środowisku procesu — może powodować błędy.")
        st.caption("Po zmianie `.env` odśwież stronę w przeglądarce.")
