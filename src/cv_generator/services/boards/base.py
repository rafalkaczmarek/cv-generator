"""Common types and helpers shared by board clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from cv_generator.config import get_settings
from cv_generator.models import BoardOffer, BoardSource


class BoardClientError(RuntimeError):
    """Raised when a board client cannot deliver results."""


@dataclass(frozen=True)
class BoardQuery:
    """User-tunable query passed to every board client.

    Board clients apply what they can (e.g. skills as keywords, city as
    location) and ignore the rest. All fields are optional.
    """

    keywords: list[str] = field(default_factory=list)
    city: str | None = None
    remote_only: bool = False
    limit_per_board: int = 150


class BoardClient(Protocol):
    """Minimal interface shared by all portal clients."""

    source: BoardSource

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        ...


def build_http_client(*, timeout: float | None = None) -> httpx.Client:
    """Build an ``httpx.Client`` pre-configured for board scraping.

    Uses the shared user-agent + timeout from :class:`Settings` and
    enables automatic redirect following (many portals redirect ``/``
    paths to a canonical one).
    """
    settings = get_settings()
    return httpx.Client(
        headers={
            "User-Agent": settings.http_user_agent,
            "Accept-Language": "pl,en;q=0.8",
            "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
        },
        timeout=timeout or settings.http_timeout_seconds,
        follow_redirects=True,
    )


__all__ = [
    "BoardClient",
    "BoardClientError",
    "BoardQuery",
    "build_http_client",
]
