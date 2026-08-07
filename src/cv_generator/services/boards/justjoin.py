"""Just Join IT client — uses the public JSON API.

Endpoint: ``GET https://justjoin.it/api/offers/v2``. When that endpoint is
unavailable we fall back to the legacy ``/api/offers``. Both return a list of
listings with a stable ``id`` we use as the external identifier.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.boards.base import (
    BoardClientError,
    BoardQuery,
    build_http_client,
)

_ENDPOINTS = (
    "https://api.justjoin.it/v2/user-panel/offers",
    "https://justjoin.it/api/offers",
)
_OFFER_URL_TEMPLATE = "https://justjoin.it/job-offer/{id}"


class JustJoinClient:
    source = BoardSource.JUSTJOIN

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        raw = self._fetch_raw()
        offers = [self._parse_offer(item) for item in raw]
        offers = [o for o in offers if o is not None]
        if query.keywords:
            offers = _filter_by_keywords(offers, query.keywords)
        if query.city:
            city = query.city.strip().lower()
            offers = [o for o in offers if _location_matches(o, city)]
        if query.remote_only:
            offers = [o for o in offers if _is_remote(o)]
        return offers[: query.limit_per_board]

    def _fetch_raw(self) -> list[dict[str, Any]]:
        client = self._client or build_http_client()
        owns_client = self._client is None
        try:
            last_error: Exception | None = None
            for url in _ENDPOINTS:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                    return _flatten_payload(payload)
                except httpx.HTTPError as exc:
                    last_error = exc
                    continue
            raise BoardClientError(f"Just Join IT API unreachable: {last_error}")
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _parse_offer(item: dict[str, Any]) -> BoardOffer | None:
        offer_id = item.get("id") or item.get("slug")
        if not offer_id:
            return None
        slug = item.get("slug") or offer_id
        url = _OFFER_URL_TEMPLATE.format(id=slug)

        skills = _extract_skills(item)
        location = _extract_location(item)
        published_at = _parse_datetime(
            item.get("publishedAt")
            or item.get("published_at")
            or item.get("newestPublishedAt")
        )

        return BoardOffer(
            source=BoardSource.JUSTJOIN,
            external_id=str(offer_id),
            url=url,
            title=str(item.get("title") or "").strip() or "(bez tytułu)",
            company=(item.get("companyName") or item.get("company_name") or None),
            location=location,
            skills=skills,
            published_at=published_at,
            salary_text=_extract_salary(item),
            workplace_type=(item.get("workplaceType") or item.get("workplace_type")),
            seniority=item.get("experienceLevel") or item.get("experience_level"),
            description_snippet=None,
            raw_payload=item,
            is_active=True,
            last_seen_at=datetime.now(UTC),
        )


def _flatten_payload(payload: Any) -> list[dict[str, Any]]:
    """JJIT returns either a plain list or an object with ``data``/``offers``."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "offers", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _extract_skills(item: dict[str, Any]) -> list[str]:
    for key in ("requiredSkills", "required_skills", "skills"):
        value = item.get(key)
        if isinstance(value, list):
            out: list[str] = []
            for entry in value:
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("skill")
                    if name:
                        out.append(str(name))
                elif isinstance(entry, str):
                    out.append(entry)
            if out:
                return out
    return []


def _extract_location(item: dict[str, Any]) -> str | None:
    city = item.get("city")
    if isinstance(city, str) and city.strip():
        return city.strip()
    multi = item.get("multilocation") or item.get("multiLocation")
    if isinstance(multi, list):
        cities = [m.get("city") for m in multi if isinstance(m, dict) and m.get("city")]
        if cities:
            return ", ".join(str(c) for c in cities[:3])
    return None


def _extract_salary(item: dict[str, Any]) -> str | None:
    salary = item.get("employmentTypes") or item.get("employment_types")
    if isinstance(salary, list) and salary:
        first = salary[0]
        if isinstance(first, dict):
            _from = first.get("from")
            _to = first.get("to")
            currency = first.get("currency", "PLN")
            if _from or _to:
                return f"{_from or '?'}-{_to or '?'} {currency}".strip()
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _location_matches(offer: BoardOffer, city: str) -> bool:
    location = (offer.location or "").lower()
    if city in location:
        return True
    raw = offer.raw_payload or {}
    multi = raw.get("multilocation") or raw.get("multiLocation") or []
    if isinstance(multi, list):
        return any(city in str(m.get("city", "")).lower() for m in multi if isinstance(m, dict))
    return False


def _is_remote(offer: BoardOffer) -> bool:
    if (offer.workplace_type or "").lower() == "remote":
        return True
    raw = offer.raw_payload or {}
    return bool(raw.get("remoteInterview") or raw.get("remote"))


def _filter_by_keywords(offers: list[BoardOffer], keywords: list[str]) -> list[BoardOffer]:
    """Keep offers whose skills or title mention at least one keyword."""
    normalized = [k.strip().lower() for k in keywords if k and k.strip()]
    if not normalized:
        return offers
    filtered: list[BoardOffer] = []
    for o in offers:
        haystack = " ".join([o.title, *o.skills]).lower()
        if any(kw in haystack for kw in normalized):
            filtered.append(o)
    return filtered


__all__ = ["JustJoinClient"]
