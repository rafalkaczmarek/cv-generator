"""Job offer schema."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class JobOffer(BaseModel):
    url: HttpUrl | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    raw_text: str

    requirements: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    def slug(self) -> str:
        """Filesystem-safe slug used for naming generated files."""
        parts = [p for p in (self.company, self.title) if p]
        base = "_".join(parts) if parts else "job"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)
        return safe.strip("_").lower()[:80] or "job"
