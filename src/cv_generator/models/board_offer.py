"""Board offer schema — a listing fetched from a Polish IT job portal.

Distinct from ``JobOffer`` (which is the LLM-analyzed, tailoring-ready form).
A ``BoardOffer`` is the raw listing metadata used for browsing and matching
without paying for an LLM call per row.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class BoardSource(StrEnum):
    """Supported Polish IT job boards."""

    JUSTJOIN = "justjoin"
    NOFLUFF = "nofluff"
    BULLDOGJOB = "bulldogjob"
    PRACUJ = "pracuj"
    THEPROTOCOL = "theprotocol"


BOARD_LABELS: dict[BoardSource, str] = {
    BoardSource.JUSTJOIN: "Just Join IT",
    BoardSource.NOFLUFF: "No Fluff Jobs",
    BoardSource.BULLDOGJOB: "Bulldogjob",
    BoardSource.PRACUJ: "pracuj.pl",
    BoardSource.THEPROTOCOL: "The Protocol",
}


class BoardOffer(BaseModel):
    """A single job listing fetched from a job board."""

    source: BoardSource
    external_id: str
    url: HttpUrl
    title: str
    company: str | None = None
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    salary_text: str | None = None
    workplace_type: str | None = None
    seniority: str | None = None
    description_snippet: str | None = None
    raw_payload: dict[str, Any] | None = None
    is_active: bool = True
    last_seen_at: datetime | None = None

    @property
    def offer_key(self) -> str:
        """Stable cross-board identifier: ``{source}:{external_id}``."""
        return f"{self.source.value}:{self.external_id}"

    @staticmethod
    def make_key(source: BoardSource | str, external_id: str) -> str:
        value = source.value if isinstance(source, BoardSource) else str(source)
        return f"{value}:{external_id}"
