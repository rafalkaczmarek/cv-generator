"""Tailored CV schema produced by the agent pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

# Placeholder company for LinkedIn/CSV projects (not a real employer).
_PROJECT_COMPANY_PLACEHOLDERS = frozenset({"projekt", "project"})


class TailoredExperience(BaseModel):
    company: str
    title: str
    location: str | None = None
    date_range: str
    bullets: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def heading(self) -> str:
        """Title alone for projects; ``title — company`` for real employers."""
        if self.company.strip().casefold() in _PROJECT_COMPANY_PLACEHOLDERS:
            return self.title
        return f"{self.title} — {self.company}"


class TailoredCV(BaseModel):
    """Final output of the pipeline, ready for the DOCX template."""

    full_name: str
    headline: str
    summary: str

    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None

    experiences: list[TailoredExperience] = Field(default_factory=list)
    education_lines: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    courses: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    match_score: int = 0
    language: str = "en"
