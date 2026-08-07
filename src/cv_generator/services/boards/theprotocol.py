"""The Protocol client — Next.js listing page hydration.

Reads offers from the ``__NEXT_DATA__`` blob embedded in
``https://theprotocol.it/filtry/...`` pages. Same defensive strategy as
Bulldogjob / pracuj.pl: parse JSON that ships with the page, not the DOM.
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

_LISTING_URL = "https://theprotocol.it/praca"
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class TheProtocolClient:
    source = BoardSource.THEPROTOCOL

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        html = self._fetch_html()
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

    def _fetch_html(self) -> str:
        client = self._client or build_http_client()
        owns_client = self._client is None
        try:
            try:
                response = client.get(_LISTING_URL)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                raise BoardClientError(f"The Protocol unreachable: {exc}") from exc
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
                if key in {"offers", "jobs", "results", "items"} and isinstance(value, list):
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
        key = str(item.get("id") or item.get("offerId") or item.get("uuid") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _looks_like_offer(item: dict[str, Any]) -> bool:
    return bool(
        (item.get("id") or item.get("offerId") or item.get("uuid"))
        and (item.get("title") or item.get("positionName") or item.get("name"))
    )


def _parse_offer(item: dict[str, Any]) -> BoardOffer | None:
    offer_id = item.get("id") or item.get("offerId") or item.get("uuid")
    if not offer_id:
        return None
    url = str(
        item.get("offerUrl")
        or item.get("url")
        or f"https://theprotocol.it/szczegoly/praca/{offer_id}"
    )

    title = str(
        item.get("title") or item.get("positionName") or item.get("name") or ""
    ).strip() or "(bez tytułu)"
    company = _extract_company(item)
    location = _extract_location(item)
    skills = _extract_skills(item)
    published_at = _parse_datetime(
        item.get("publishedAt") or item.get("publicationDate") or item.get("published")
    )

    return BoardOffer(
        source=BoardSource.THEPROTOCOL,
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
    for key in ("locationText", "city", "location"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("workplaces", "locations", "cities"):
        values = item.get(key)
        if isinstance(values, list) and values:
            names: list[str] = []
            for v in values:
                if isinstance(v, str):
                    names.append(v)
                elif isinstance(v, dict):
                    name = v.get("city") or v.get("name")
                    if name:
                        names.append(str(name))
            if names:
                return ", ".join(names[:3])
    return None


def _extract_skills(item: dict[str, Any]) -> list[str]:
    for key in ("technologies", "skills", "requiredTechnologies", "tags", "mainTechnologies"):
        value = item.get(key)
        if isinstance(value, list):
            out: list[str] = []
            for entry in value:
                if isinstance(entry, str):
                    out.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("technology") or entry.get("value")
                    if name:
                        out.append(str(name))
            if out:
                return out
    return []


def _extract_salary(item: dict[str, Any]) -> str | None:
    salary = item.get("salary") or item.get("salaryText") or item.get("salaries")
    if isinstance(salary, str):
        return salary.strip() or None
    if isinstance(salary, list) and salary:
        salary = salary[0]
    if isinstance(salary, dict):
        _from = salary.get("from") or salary.get("min")
        _to = salary.get("to") or salary.get("max")
        currency = salary.get("currency", "PLN")
        if _from or _to:
            return f"{_from or '?'}-{_to or '?'} {currency}".strip()
    return None


def _extract_workplace(item: dict[str, Any]) -> str | None:
    for key in ("workModes", "workplaceTypes", "workMode"):
        value = item.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return str(first.get("name") or first.get("value") or "")
    return None


def _extract_seniority(item: dict[str, Any]) -> str | None:
    value = item.get("experienceLevel") or item.get("seniority") or item.get("positionLevel")
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


__all__ = ["TheProtocolClient"]
