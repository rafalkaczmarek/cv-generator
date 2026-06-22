"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (…/src/cv_generator/config.py → parents[2]).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_provider: Literal["openai", "anthropic", "github"] = "openai"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # GitHub Models (OpenAI-compatible inference endpoint).
    # Uses a GitHub personal access token with the `models:read` scope.
    github_token: str | None = None
    github_model: str = "openai/gpt-4.1-mini"
    github_base_url: str = "https://models.github.ai/inference"

    app_data_dir: Path = Field(default=Path("./data"))
    app_output_dir: Path = Field(default=Path("./output"))
    app_templates_dir: Path = Field(default=Path("./templates"))
    app_language: str = "pl"

    http_timeout_seconds: int = 15
    http_user_agent: str = "Mozilla/5.0 (compatible; CVGeneratorBot/0.1)"

    min_match_score: int = 70
    max_tailor_iterations: int = 2

    google_credentials_path: Path = Field(default=Path("./secrets/google_credentials.json"))
    google_token_path: Path = Field(default=Path("./secrets/google_token.json"))
    google_drive_template_id: str | None = None

    def ensure_dirs(self) -> None:
        for d in (self.app_data_dir, self.app_output_dir, self.app_templates_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None
_env_mtime: float | None = None


def get_settings() -> Settings:
    """Return settings, reloading when `.env` changes on disk."""
    global _settings, _env_mtime

    mtime = ENV_FILE.stat().st_mtime if ENV_FILE.exists() else 0.0
    if _settings is None or mtime != _env_mtime:
        _settings = Settings()
        _env_mtime = mtime
        _clear_llm_cache()

    _settings.ensure_dirs()
    return _settings


def describe_llm_provider() -> str:
    """Short label for the active LLM provider (UI diagnostics)."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        return f"OpenAI ({settings.openai_model})"
    if settings.llm_provider == "github":
        return f"GitHub Models ({settings.github_model})"
    if settings.llm_provider == "anthropic":
        return f"Anthropic ({settings.anthropic_model})"
    return settings.llm_provider


def _clear_llm_cache() -> None:
    try:
        from cv_generator.services.llm import clear_llm_cache

        clear_llm_cache()
    except ImportError:
        pass
