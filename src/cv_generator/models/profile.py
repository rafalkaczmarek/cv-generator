"""User profile schema.

The profile is the source of truth for everything that may appear in a CV.
Agents are forbidden from inventing data outside of this structure.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class Experience(BaseModel):
    company: str
    title: str
    location: str | None = None
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    summary: str | None = None
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    @field_validator("bullets", "technologies", mode="before")
    @classmethod
    def _normalize_list(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [line.strip() for line in v.splitlines() if line.strip()]
        return list(v)  # type: ignore[arg-type]


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    issued: date | None = None
    url: HttpUrl | None = None


class Profile(BaseModel):
    full_name: str
    headline: str | None = None
    summary: str | None = None

    email: EmailStr | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    website_url: HttpUrl | None = None

    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)

    @field_validator("skills", "languages", mode="before")
    @classmethod
    def _normalize_list(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [item.strip() for item in v.replace("\n", ",").split(",") if item.strip()]
        return list(v)  # type: ignore[arg-type]

    def sorted_experiences(self) -> list[Experience]:
        """Most recent first; current positions sorted before past ones."""
        return sorted(
            self.experiences,
            key=lambda e: (e.is_current, e.end_date or date.max, e.start_date),
            reverse=True,
        )
