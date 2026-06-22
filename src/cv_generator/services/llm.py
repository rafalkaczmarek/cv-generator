"""LLM client factory."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from cv_generator.config import get_settings

_PLACEHOLDER_KEYS = frozenset({"sk-...", "sk-your-key-here", "changeme"})


def _reject_placeholder_key(key: str, *, env_var: str) -> None:
    stripped = key.strip()
    if not stripped or stripped in _PLACEHOLDER_KEYS or stripped.endswith("..."):
        raise RuntimeError(
            f"{env_var} wygląda na placeholder (np. sk-...). "
            f"Ustaw prawdziwy klucz w pliku .env w katalogu projektu."
        )


def get_llm(*, json_mode: bool = False) -> BaseChatModel:
    settings = get_settings()
    extra_kwargs: dict = {}
    if json_mode:
        extra_kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY nie jest ustawiony. Ustaw go w .env lub zmień LLM_PROVIDER."
            )
        _reject_placeholder_key(settings.openai_api_key, env_var="OPENAI_API_KEY")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
            **extra_kwargs,
        )

    if settings.llm_provider == "github":
        if not settings.github_token:
            raise RuntimeError(
                "GITHUB_TOKEN nie jest ustawiony. Wygeneruj PAT z uprawnieniem models:read."
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.github_model,
            api_key=settings.github_token,
            base_url=settings.github_base_url,
            temperature=0.2,
            **extra_kwargs,
        )

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY nie jest ustawiony. Ustaw go w .env lub zmień LLM_PROVIDER."
            )
        _reject_placeholder_key(settings.anthropic_api_key, env_var="ANTHROPIC_API_KEY")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.2,
        )

    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


def get_json_llm() -> BaseChatModel:
    settings = get_settings()
    if settings.llm_provider in ("openai", "github"):
        return get_llm(json_mode=True)
    return get_llm()
