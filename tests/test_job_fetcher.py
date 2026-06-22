"""Tests for job-offer URL fetching."""

from __future__ import annotations

import httpx
import pytest

from cv_generator.services import job_fetcher


class _FakeHttpResponse:
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com/job")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeHttpClient:
    def __init__(self, response: _FakeHttpResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeHttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, _url: str) -> _FakeHttpResponse:
        return self._response


def test_fetch_job_text_extracts_readable_content(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<html><body><h1>Senior Python Engineer</h1></body></html>"
    monkeypatch.setattr(
        job_fetcher.httpx,
        "Client",
        lambda **kwargs: _FakeHttpClient(_FakeHttpResponse(html)),
    )
    monkeypatch.setattr(
        job_fetcher.trafilatura,
        "extract",
        lambda _html, **kwargs: "Senior Python Engineer at GammaTech",
    )

    text = job_fetcher.fetch_job_text("https://example.com/job/123")

    assert "Senior Python Engineer" in text


def test_fetch_job_text_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_fetcher.httpx,
        "Client",
        lambda **kwargs: _FakeHttpClient(_FakeHttpResponse("", status_code=404)),
    )

    with pytest.raises(job_fetcher.JobFetchError, match="Failed to fetch"):
        job_fetcher.fetch_job_text("https://example.com/missing")


def test_fetch_job_text_raises_when_extraction_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_fetcher.httpx,
        "Client",
        lambda **kwargs: _FakeHttpClient(_FakeHttpResponse("<html></html>")),
    )
    monkeypatch.setattr(job_fetcher.trafilatura, "extract", lambda _html, **kwargs: "")

    with pytest.raises(job_fetcher.JobFetchError, match="Could not extract"):
        job_fetcher.fetch_job_text("https://example.com/empty")
