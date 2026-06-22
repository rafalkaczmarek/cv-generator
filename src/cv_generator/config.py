"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (…/src/cv_generator/config.py → parents[2]).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

_ENV_FIELD_MAP: dict[str, str] = {
    "LLM_PROVIDER": "llm_provider",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_MODEL": "openai_model",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "ANTHROPIC_MODEL": "anthropic_model",
    "GITHUB_TOKEN": "github_token",
    "GITHUB_MODEL": "github_model",
    "GITHUB_BASE_URL": "github_base_url",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_provider: Literal["openai", "anthropic", "github"] = "github"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
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


def _parse_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _apply_env_file(settings: Settings) -> None:
    """Force LLM fields from `.env` — beats IDE-injected process env."""
    file_values = _parse_env_file()
    for env_key, field_name in _ENV_FIELD_MAP.items():
        if env_key not in file_values:
            continue
        raw = file_values[env_key]
        if not raw and (field_name.endswith("_api_key") or field_name == "github_token"):
            setattr(settings, field_name, None)
        else:
            setattr(settings, field_name, raw)
    if settings.llm_provider != "openai":
        settings.openai_api_key = None


def _scrub_openai_process_env() -> None:
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(key, None)


def _reload_env_into_process() -> None:
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
    if _parse_env_file().get("LLM_PROVIDER", "github") != "openai":
        _scrub_openai_process_env()


def get_settings() -> Settings:
    """Load settings fresh on every call (Streamlit reruns keep module state)."""
    _reload_env_into_process()
    settings = Settings()
    _apply_env_file(settings)
    if settings.llm_provider != "openai":
        _scrub_openai_process_env()
    settings.ensure_dirs()
    return settings
