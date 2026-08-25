"""Listing filters shared by the Oferty tab and the fetch orchestrator.

The UI always shows only offers published today or yesterday whose title or
skills mention at least one of the user-supplied keywords.
"""

from __future__ import annotations

from datetime import date, datetime

from cv_generator.models import BoardOffer

RECENT_OFFER_MAX_AGE_DAYS = 1


def _calendar_date(value: datetime, *, reference: datetime) -> date:
    """Calendar day of ``value`` in the same timezone as ``reference``."""
    if value.tzinfo is None and reference.tzinfo is None:
        return value.date()
    if value.tzinfo is None:
        tz = reference.tzinfo
        return value.replace(tzinfo=tz).date() if tz is not None else value.date()
    if reference.tzinfo is None:
        return value.astimezone().date()
    return value.astimezone(reference.tzinfo).date()


def is_recently_published(offer: BoardOffer, *, now: datetime | None = None) -> bool:
    """True when ``published_at`` falls on today or yesterday (local calendar)."""
    if offer.published_at is None:
        return False
    current = now if now is not None else datetime.now().astimezone()
    offer_day = _calendar_date(offer.published_at, reference=current)
    today = _calendar_date(current, reference=current)
    age_days = (today - offer_day).days
    return 0 <= age_days <= RECENT_OFFER_MAX_AGE_DAYS


def offer_matches_keywords(offer: BoardOffer, keywords: list[str]) -> bool:
    """True when title or skills contain at least one of ``keywords``."""
    normalized = [k.strip().lower() for k in keywords if k and k.strip()]
    if not normalized:
        return False
    parts = [offer.title, *(offer.skills or [])]
    if offer.description_snippet:
        parts.append(offer.description_snippet)
    haystack = " ".join(parts).lower()
    return any(kw in haystack for kw in normalized)


def filter_board_offers(
    offers: list[BoardOffer],
    *,
    keywords: list[str] | None = None,
    now: datetime | None = None,
    require_keywords: bool = True,
) -> list[BoardOffer]:
    """Keep offers from today/yesterday that match ``keywords``.

    When ``require_keywords`` is true and the keyword list is empty, nothing
    is returned. When false, an empty keyword list skips the keyword check
    (used by the fetch orchestrator for programmatic refreshes).
    """
    normalized = [k.strip() for k in (keywords or []) if k and k.strip()]
    if require_keywords and not normalized:
        return []
    filtered: list[BoardOffer] = []
    for offer in offers:
        if not is_recently_published(offer, now=now):
            continue
        if normalized and not offer_matches_keywords(offer, normalized):
            continue
        filtered.append(offer)
    return filtered


__all__ = [
    "RECENT_OFFER_MAX_AGE_DAYS",
    "filter_board_offers",
    "is_recently_published",
    "offer_matches_keywords",
]
