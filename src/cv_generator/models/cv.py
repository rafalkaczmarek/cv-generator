"""Tailored CV schema produced by the agent pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TailoredExperience(BaseModel):
    company: str
    title: str
    location: str | None = None
    date_range: str
    bullets: list[str] = Field(default_factory=list)


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
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    match_score: int = 0
