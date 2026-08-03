"""LLM client factory."""

from __future__ import annotations

import json

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

    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY nie jest ustawiony. "
                "Wygeneruj klucz na https://aistudio.google.com/apikey."
            )
        _reject_placeholder_key(settings.gemini_api_key, env_var="GEMINI_API_KEY")
        from langchain_google_genai import ChatGoogleGenerativeAI

        gemini_kwargs: dict = {}
        if json_mode:
            gemini_kwargs["response_mime_type"] = "application/json"
        # Omit temperature: gemini-3.6-flash ignores custom sampling and warns if set.
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            **gemini_kwargs,
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

    if settings.llm_provider == "stub":
        from cv_generator.services.stub_llm import get_stub_llm

        return get_stub_llm()

    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


def get_json_llm() -> BaseChatModel:
    settings = get_settings()
    if settings.llm_provider in ("openai", "gemini"):
        return get_llm(json_mode=True)
    return get_llm()


def message_content_to_text(content: object) -> str:
    """Normalize LangChain message content (str or content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def parse_llm_json(content: object) -> dict:
    """Parse JSON from an LLM response, including Gemini content-block lists."""
    text = message_content_to_text(content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object from LLM, got {type(parsed).__name__}")
    return parsed
