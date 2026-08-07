"""No Fluff Jobs client — POST /api/search/posting.

Uses the publicly reachable JSON search endpoint. Optionally hits the
per-slug detail endpoint when descriptions are needed for tailoring.
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

_SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
_OFFER_URL_TEMPLATE = "https://nofluffjobs.com/pl/job/{url_slug}"


class NoFluffClient:
    source = BoardSource.NOFLUFF

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        raw = self._fetch_search(query)
        offers = [self._parse_offer(item) for item in raw]
        return [o for o in offers if o is not None][: query.limit_per_board]

    def _fetch_search(self, query: BoardQuery) -> list[dict[str, Any]]:
        client = self._client or build_http_client()
        owns_client = self._client is None
        try:
            body = {"page": 1, "criteriaSearch": {}, "rawSearch": ""}
            if query.keywords:
                body["rawSearch"] = " ".join(query.keywords)
            if query.remote_only:
                body["criteriaSearch"] = {"remote": ["fully"]}
            params = {"salaryCurrency": "PLN", "salaryPeriod": "month", "region": "pl"}

            collected: list[dict[str, Any]] = []
            try:
                for page in range(1, 6):
                    body["page"] = page
                    response = client.post(_SEARCH_URL, params=params, json=body)
                    response.raise_for_status()
                    payload = response.json()
                    postings = _extract_postings(payload)
                    collected.extend(postings)
                    if not postings:
                        break
                    total_pages = payload.get("totalPages") or payload.get("pages") or 1
                    if page >= int(total_pages):
                        break
                    if len(collected) >= query.limit_per_board * 2:
                        break
            except httpx.HTTPError as exc:
                raise BoardClientError(f"No Fluff Jobs API failed: {exc}") from exc
            return collected
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _parse_offer(item: dict[str, Any]) -> BoardOffer | None:
        posting_id = item.get("id") or item.get("_id")
        url_slug = item.get("url") or item.get("slug")
        if not posting_id and not url_slug:
            return None
        external_id = str(posting_id or url_slug)
        offer_url = _OFFER_URL_TEMPLATE.format(url_slug=(url_slug or external_id))

        title = item.get("title") or item.get("name") or "(bez tytułu)"
        company = _extract_company(item)
        location = _extract_location(item)
        skills = _extract_skills(item)
        published_at = _parse_datetime(item.get("posted") or item.get("createdAt"))
        salary = _extract_salary(item)
        seniority = _extract_seniority(item)

        return BoardOffer(
            source=BoardSource.NOFLUFF,
            external_id=external_id,
            url=offer_url,
            title=str(title).strip(),
            company=company,
            location=location,
            skills=skills,
            published_at=published_at,
            salary_text=salary,
            workplace_type=_extract_workplace(item),
            seniority=seniority,
            description_snippet=None,
            raw_payload=item,
            is_active=True,
            last_seen_at=datetime.now(UTC),
        )


def _extract_postings(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("postings", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _extract_company(item: dict[str, Any]) -> str | None:
    for key in ("companyName", "company", "employer"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name") or value.get("company_name")
            if name:
                return str(name)
    return None


def _extract_location(item: dict[str, Any]) -> str | None:
    location = item.get("location")
    if isinstance(location, dict):
        places = location.get("places") or []
        if isinstance(places, list) and places:
            cities: list[str] = []
            for p in places:
                if isinstance(p, dict):
                    city = p.get("city") or p.get("street", {}).get("city")
                    if city:
                        cities.append(str(city))
            if cities:
                return ", ".join(cities[:3])
        if location.get("fullyRemote"):
            return "Zdalnie"
    return None


def _extract_skills(item: dict[str, Any]) -> list[str]:
    """Union skills across all known keys (NFJ splits them into several)."""
    collected: list[str] = []
    for key in ("technology", "tiles", "mustHaves", "must_haves"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            collected.append(value.strip())
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    collected.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("value")
                    if name:
                        collected.append(str(name))
    seen: set[str] = set()
    unique: list[str] = []
    for skill in collected:
        key = skill.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(skill.strip())
    return unique


def _extract_salary(item: dict[str, Any]) -> str | None:
    salary = item.get("salary") or item.get("salaries")
    if isinstance(salary, list) and salary:
        salary = salary[0]
    if isinstance(salary, dict):
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "PLN")
        period = salary.get("period") or salary.get("type") or ""
        if _from or _to:
            return f"{_from or '?'}-{_to or '?'} {currency} {period}".strip()
    return None


def _extract_workplace(item: dict[str, Any]) -> str | None:
    location = item.get("location") or {}
    if isinstance(location, dict) and location.get("fullyRemote"):
        return "remote"
    return None


def _extract_seniority(item: dict[str, Any]) -> str | None:
    for key in ("seniority", "experience", "level"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


__all__ = ["NoFluffClient"]
