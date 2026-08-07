"""pracuj.pl (IT vertical) client — Next.js listing page hydration.

The IT-focused listing at ``https://it.pracuj.pl/praca`` embeds a
``__NEXT_DATA__`` payload containing the same offers displayed on the page.
We parse that payload so the client is not brittle to CSS/DOM changes.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.boards.base import (
    BoardClientError,
    BoardQuery,
    build_http_client,
)

_LISTING_URL = "https://it.pracuj.pl/praca"
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class PracujClient:
    source = BoardSource.PRACUJ

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        html = self._fetch_html(query)
        raw_offers = _extract_offers_from_next_data(html)
        parsed: list[BoardOffer] = []
        for item in raw_offers:
            offer = _parse_offer(item)
            if offer:
                parsed.append(offer)

        if query.keywords:
            parsed = _filter_by_keywords(parsed, query.keywords)
        if query.city:
            city = query.city.strip().lower()
            parsed = [o for o in parsed if city in (o.location or "").lower()]
        if query.remote_only:
            parsed = [o for o in parsed if _is_remote(o)]
        return parsed[: query.limit_per_board]

    def _fetch_html(self, query: BoardQuery) -> str:
        client = self._client or build_http_client()
        owns_client = self._client is None
        try:
            params: dict[str, str] = {}
            if query.city:
                params["cc"] = query.city
            try:
                response = client.get(_LISTING_URL, params=params)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                raise BoardClientError(f"pracuj.pl unreachable: {exc}") from exc
        finally:
            if owns_client:
                client.close()


def _extract_offers_from_next_data(html: str) -> list[dict[str, Any]]:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    candidates: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"groupedOffers", "offers", "jobOffers", "items"} and isinstance(
                    value, list
                ):
                    for item in value:
                        if isinstance(item, dict) and _looks_like_offer(item):
                            candidates.append(item)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in candidates:
        key = str(item.get("groupId") or item.get("id") or item.get("offerId") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _looks_like_offer(item: dict[str, Any]) -> bool:
    return bool(
        (item.get("id") or item.get("groupId") or item.get("offerId"))
        and (item.get("jobTitle") or item.get("title") or item.get("positionName"))
    )


def _parse_offer(item: dict[str, Any]) -> BoardOffer | None:
    offer_id = item.get("groupId") or item.get("id") or item.get("offerId")
    if not offer_id:
        return None
    url = str(
        item.get("offerAbsoluteUri")
        or item.get("offerUrl")
        or f"https://it.pracuj.pl/praca/oferta,oferta,{offer_id}"
    )

    title = str(
        item.get("jobTitle") or item.get("title") or item.get("positionName") or ""
    ).strip() or "(bez tytułu)"
    company = _extract_company(item)
    location = _extract_location(item)
    skills = _extract_skills(item)
    published_at = _parse_datetime(
        item.get("lastPublicated") or item.get("publicationDate") or item.get("publishedAt")
    )

    return BoardOffer(
        source=BoardSource.PRACUJ,
        external_id=str(offer_id),
        url=url,
        title=title,
        company=company,
        location=location,
        skills=skills,
        published_at=published_at,
        salary_text=_extract_salary(item),
        workplace_type=_extract_workplace(item),
        seniority=_extract_seniority(item),
        description_snippet=None,
        raw_payload=item,
        is_active=True,
        last_seen_at=datetime.now(UTC),
    )


def _extract_company(item: dict[str, Any]) -> str | None:
    for key in ("companyName", "company", "employer"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name")
            if name:
                return str(name)
    return None


def _extract_location(item: dict[str, Any]) -> str | None:
    for key in ("displayWorkplace", "cityName", "location"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("workplaces", "cities", "locations"):
        values = item.get(key)
        if isinstance(values, list) and values:
            names: list[str] = []
            for v in values:
                if isinstance(v, str):
                    names.append(v)
                elif isinstance(v, dict):
                    name = v.get("cityName") or v.get("city") or v.get("name")
                    if name:
                        names.append(str(name))
            if names:
                return ", ".join(names[:3])
    return None


def _extract_skills(item: dict[str, Any]) -> list[str]:
    for key in ("technologies", "skills", "requiredTechnologies", "tags"):
        value = item.get(key)
        if isinstance(value, list):
            out: list[str] = []
            for entry in value:
                if isinstance(entry, str):
                    out.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("technology")
                    if name:
                        out.append(str(name))
            if out:
                return out
    return []


def _extract_salary(item: dict[str, Any]) -> str | None:
    salary = item.get("salary") or item.get("salaryDisplayText") or item.get("salaryText")
    if isinstance(salary, str):
        return salary.strip() or None
    if isinstance(salary, dict):
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "PLN")
        if _from or _to:
            return f"{_from or '?'}-{_to or '?'} {currency}".strip()
    return None


def _extract_workplace(item: dict[str, Any]) -> str | None:
    for key in ("workModes", "workplaceTypes", "workMode"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return str(first.get("name") or first.get("value") or "")
    return None


def _extract_seniority(item: dict[str, Any]) -> str | None:
    value = item.get("positionLevels") or item.get("seniority") or item.get("experienceLevel")
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("name") or first.get("value") or "")
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


def _is_remote(offer: BoardOffer) -> bool:
    wm = (offer.workplace_type or "").lower()
    return "remote" in wm or "zdaln" in wm


def _filter_by_keywords(offers: list[BoardOffer], keywords: list[str]) -> list[BoardOffer]:
    normalized = [k.strip().lower() for k in keywords if k and k.strip()]
    if not normalized:
        return offers
    filtered: list[BoardOffer] = []
    for o in offers:
        haystack = " ".join([o.title, *o.skills]).lower()
        if any(kw in haystack for kw in normalized):
            filtered.append(o)
    return filtered


__all__ = ["PracujClient"]
