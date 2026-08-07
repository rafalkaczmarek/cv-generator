"""Tests for individual board clients.

The JSON APIs (Just Join IT, No Fluff Jobs) are exercised with hand-crafted
``httpx.MockTransport`` responses. The scraping clients (Bulldogjob,
pracuj.pl, The Protocol) are exercised against a synthetic HTML page that
embeds a minimal ``__NEXT_DATA__`` payload — enough to prove field mapping
without shipping real portal HTML.
"""

from __future__ import annotations

import json

import httpx
import pytest

from cv_generator.models import BoardSource
from cv_generator.services.boards import BoardQuery
from cv_generator.services.boards.bulldogjob import BulldogjobClient
from cv_generator.services.boards.justjoin import JustJoinClient
from cv_generator.services.boards.nofluff import NoFluffClient
from cv_generator.services.boards.pracuj import PracujClient
from cv_generator.services.boards.theprotocol import TheProtocolClient


def _client_with(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, timeout=5.0)


# --- Just Join IT ---------------------------------------------------------


def test_justjoin_client_parses_public_api_payload() -> None:
    payload = {
        "data": [
            {
                "guid": "g-1",
                "slug": "abc-1",
                "title": "Senior Python Developer",
                "companyName": "GammaTech",
                "city": "Warszawa",
                "publishedAt": "2026-02-01T10:00:00Z",
                "workplaceType": "remote",
                "experienceLevel": "senior",
                "requiredSkills": [{"name": "Python"}, {"name": "FastAPI"}],
                "employmentTypes": [
                    {
                        "from": None,
                        "to": None,
                        "currency": "EUR",
                        "currencySource": "conversion",
                    },
                    {
                        "from": 20000,
                        "to": 25000,
                        "currency": "PLN",
                        "currencySource": "original",
                    },
                ],
            },
            {
                "guid": "g-2",
                "slug": "abc-2",
                "title": "Junior React Dev",
                "companyName": "FE Corp",
                "city": "Kraków",
                "publishedAt": "2026-01-15T09:00:00Z",
                "requiredSkills": [{"name": "React"}, {"name": "TypeScript"}],
            },
        ],
        "meta": {"next": {"cursor": None}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/candidate-api/offers" in str(request.url)
        return httpx.Response(200, json=payload)

    client = JustJoinClient(client=_client_with(handler))
    offers = client.fetch_offers(query=BoardQuery(keywords=["python"]))

    assert len(offers) == 1
    offer = offers[0]
    assert offer.source is BoardSource.JUSTJOIN
    assert offer.external_id == "abc-1"
    assert offer.company == "GammaTech"
    assert "Python" in offer.skills
    assert offer.salary_text == "20000-25000 PLN"
    assert offer.published_at is not None
    assert offer.url.host == "justjoin.it"


def test_justjoin_client_handles_wrapped_payload() -> None:
    payload = {
        "data": [{"slug": "x", "title": "Dev", "requiredSkills": []}],
        "meta": {"next": {"cursor": None}},
    }

    client = JustJoinClient(
        client=_client_with(lambda req: httpx.Response(200, json=payload))
    )
    offers = client.fetch_offers(query=BoardQuery())
    assert len(offers) == 1
    assert offers[0].external_id == "x"


def test_justjoin_client_paginates_candidate_api() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        from_param = request.url.params.get("from", "0")
        if from_param == "0":
            return httpx.Response(
                200,
                json={
                    "data": [{"slug": "1", "title": "Dev A", "requiredSkills": []}],
                    "meta": {"next": {"cursor": 1, "itemsCount": 1}},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{"slug": "2", "title": "Dev B", "requiredSkills": []}],
                "meta": {"next": {"cursor": None}},
            },
        )

    client = JustJoinClient(client=_client_with(handler))
    offers = client.fetch_offers(query=BoardQuery(limit_per_board=2))
    assert [o.external_id for o in offers] == ["1", "2"]
    assert len(calls) == 2


# --- No Fluff Jobs --------------------------------------------------------


def test_nofluff_client_parses_search_payload() -> None:
    payload = {
        "totalPages": 1,
        "totalCount": 1,
        "postings": [
            {
                "id": "posting-1",
                "url": "python-dev-warsaw",
                "title": "Python Developer",
                "companyName": "AlphaSoft",
                "posted": 1_700_000_000_000,
                "location": {
                    "fullyRemote": False,
                    "places": [{"city": "Warszawa"}],
                },
                "technology": "Python",
                "seniority": ["senior"],
                "salary": {"from": 18000, "to": 22000, "currency": "PLN", "period": "month"},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content.decode() or "{}")
        assert body["page"] >= 1
        return httpx.Response(200, json=payload)

    client = NoFluffClient(client=_client_with(handler))
    offers = client.fetch_offers(query=BoardQuery(keywords=["python"]))

    assert len(offers) == 1
    offer = offers[0]
    assert offer.source is BoardSource.NOFLUFF
    assert offer.external_id == "posting-1"
    assert offer.company == "AlphaSoft"
    assert offer.location == "Warszawa"
    assert "Python" in offer.skills
    assert offer.salary_text and "PLN" in offer.salary_text
    assert str(offer.url).startswith("https://nofluffjobs.com/pl/job/")


# --- Bulldogjob / pracuj.pl / The Protocol scraping -----------------------


def _next_data_html(payload: dict) -> str:
    return (
        "<html><head></head><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        "</body></html>"
    )


def test_bulldogjob_client_extracts_offers_from_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "jobs": [
                    {
                        "id": "job-1",
                        "slug": "job-1",
                        "position": "Backend Engineer",
                        "companyName": "BullCorp",
                        "city": "Wrocław",
                        "publishedAt": "2026-03-01T08:00:00Z",
                        "technologies": [{"name": "Python"}, {"name": "Kubernetes"}],
                        "experienceLevel": "senior",
                    },
                    {"id": "ignored"},
                ]
            }
        }
    }
    html = _next_data_html(payload)
    client = BulldogjobClient(
        client=_client_with(lambda req: httpx.Response(200, text=html))
    )
    offers = client.fetch_offers(query=BoardQuery(keywords=["python"]))
    assert len(offers) == 1
    assert offers[0].external_id == "job-1"
    assert offers[0].company == "BullCorp"
    assert "Kubernetes" in offers[0].skills


def test_pracuj_client_extracts_offers_from_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "data": {
                    "groupedOffers": [
                        {
                            "groupId": "grp-42",
                            "jobTitle": "Senior Python",
                            "companyName": "PracujCo",
                            "displayWorkplace": "Warszawa",
                            "lastPublicated": "2026-02-20T09:00:00Z",
                            "technologies": ["Python", "Django"],
                            "offerAbsoluteUri": "https://it.pracuj.pl/praca/oferta,42",
                        }
                    ]
                }
            }
        }
    }
    html = _next_data_html(payload)
    client = PracujClient(
        client=_client_with(lambda req: httpx.Response(200, text=html))
    )
    offers = client.fetch_offers(query=BoardQuery())
    assert len(offers) == 1
    assert offers[0].external_id == "grp-42"
    assert offers[0].skills == ["Python", "Django"]
    assert str(offers[0].url).endswith("42")


def test_theprotocol_client_extracts_offers_from_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "offers": [
                    {
                        "id": "proto-9",
                        "title": "DevOps Engineer",
                        "companyName": "ProtoCo",
                        "locationText": "Kraków",
                        "publishedAt": "2026-04-01T00:00:00Z",
                        "technologies": [{"name": "Kubernetes"}, {"name": "Terraform"}],
                    }
                ]
            }
        }
    }
    html = _next_data_html(payload)
    client = TheProtocolClient(
        client=_client_with(lambda req: httpx.Response(200, text=html))
    )
    offers = client.fetch_offers(query=BoardQuery())
    assert len(offers) == 1
    assert offers[0].external_id == "proto-9"
    assert offers[0].location == "Kraków"


def test_scraper_returns_empty_when_next_data_missing() -> None:
    client = BulldogjobClient(
        client=_client_with(lambda req: httpx.Response(200, text="<html>no data</html>"))
    )
    assert client.fetch_offers(query=BoardQuery()) == []


def test_client_raises_board_client_error_on_http_failure() -> None:
    from cv_generator.services.boards.base import BoardClientError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server down")

    client = BulldogjobClient(client=_client_with(handler))
    with pytest.raises(BoardClientError):
        client.fetch_offers(query=BoardQuery())
