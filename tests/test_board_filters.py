"""Filters that keep only recent, keyword-matching board offers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.boards.filters import (
    filter_board_offers,
    is_recently_published,
    offer_matches_keywords,
)

_NOW = datetime(2026, 8, 24, 14, 0)


def _offer(
    *,
    external_id: str = "1",
    title: str = "Python Dev",
    skills: list[str] | None = None,
    published_at: datetime | None = _NOW,
    description_snippet: str | None = None,
) -> BoardOffer:
    return BoardOffer(
        source=BoardSource.JUSTJOIN,
        external_id=external_id,
        url=f"https://example.com/offer/{external_id}",
        title=title,
        skills=["Python"] if skills is None else skills,
        published_at=published_at,
        description_snippet=description_snippet,
    )


def test_is_recently_published_keeps_today_and_yesterday() -> None:
    today = _offer(external_id="today", published_at=_NOW)
    yesterday = _offer(external_id="yday", published_at=_NOW - timedelta(days=1))
    older = _offer(external_id="old", published_at=_NOW - timedelta(days=2))
    missing = _offer(external_id="none", published_at=None)

    assert is_recently_published(today, now=_NOW) is True
    assert is_recently_published(yesterday, now=_NOW) is True
    assert is_recently_published(older, now=_NOW) is False
    assert is_recently_published(missing, now=_NOW) is False


def test_is_recently_published_uses_reference_timezone() -> None:
    """UTC evening that is already the next calendar day in CEST stays 'today'."""
    warsaw = timezone(timedelta(hours=2))
    now = datetime(2026, 8, 24, 1, 0, tzinfo=warsaw)
    published = datetime(2026, 8, 23, 22, 30, tzinfo=UTC)
    offer = _offer(published_at=published)
    assert is_recently_published(offer, now=now) is True


def test_offer_matches_keywords_in_title_or_skills() -> None:
    offer = _offer(title="Backend Engineer", skills=["FastAPI", "PostgreSQL"])
    assert offer_matches_keywords(offer, ["python"]) is False
    assert offer_matches_keywords(offer, ["FastAPI"]) is True
    assert offer_matches_keywords(offer, ["backend"]) is True


def test_offer_matches_keywords_in_description_snippet() -> None:
    offer = _offer(
        title="Engineer",
        skills=["SQL"],
        description_snippet="We use Kubernetes daily.",
    )
    assert offer_matches_keywords(offer, ["Kubernetes"]) is True


def test_offer_matches_keywords_rejects_empty_list() -> None:
    assert offer_matches_keywords(_offer(), []) is False


def test_filter_board_offers_applies_date_and_keywords() -> None:
    keep = _offer(external_id="keep", title="Python backend", published_at=_NOW)
    old = _offer(
        external_id="old",
        title="Python backend",
        published_at=_NOW - timedelta(days=5),
    )
    mismatch = _offer(
        external_id="go",
        title="Go engineer",
        skills=["Go"],
        published_at=_NOW,
    )
    results = filter_board_offers(
        [keep, old, mismatch],
        keywords=["Python"],
        now=_NOW,
    )
    assert [o.external_id for o in results] == ["keep"]


def test_filter_board_offers_requires_keywords_by_default() -> None:
    offer = _offer(published_at=_NOW)
    assert filter_board_offers([offer], keywords=[], now=_NOW) == []
    assert filter_board_offers([offer], keywords=None, now=_NOW) == []


def test_filter_board_offers_can_skip_keyword_requirement() -> None:
    today = _offer(external_id="today", title="Anything", skills=["Go"], published_at=_NOW)
    old = _offer(
        external_id="old",
        title="Python",
        published_at=_NOW - timedelta(days=3),
    )
    results = filter_board_offers(
        [today, old],
        keywords=[],
        now=_NOW,
        require_keywords=False,
    )
    assert [o.external_id for o in results] == ["today"]
