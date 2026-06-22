"""Tests for JobAnalyzer with the LLM stubbed out."""

from __future__ import annotations

import pytest

from cv_generator.agents import job_analyzer
from tests.fake_llm import FakeLLM


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    payload = (
        '{"title": "Senior Python Engineer", "company": "GammaTech", '
        '"location": "Remote", "requirements": ["Python", "FastAPI"], '
        '"nice_to_have": ["Terraform"], "responsibilities": ["Design APIs"], '
        '"keywords": ["python", "fastapi", "kubernetes"]}'
    )
    llm = FakeLLM(payload)

    def _factory():
        return llm

    monkeypatch.setattr(job_analyzer, "get_json_llm", _factory)
    return llm


def test_analyze_job_from_raw_text(fake_llm) -> None:
    offer = job_analyzer.analyze_job(url=None, raw_text="We need a Python engineer.")
    assert offer.title == "Senior Python Engineer"
    assert offer.company == "GammaTech"
    assert "Python" in offer.requirements
    assert "fastapi" in [k.lower() for k in offer.keywords]


def test_analyze_job_requires_some_input() -> None:
    with pytest.raises(ValueError):
        job_analyzer.analyze_job(url=None, raw_text=None)


def test_analyze_job_handles_markdown_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fenced = '```json\n{"title": "Backend", "company": "X", "requirements": []}\n```'
    monkeypatch.setattr(job_analyzer, "get_json_llm", lambda: FakeLLM(fenced))
    offer = job_analyzer.analyze_job(url=None, raw_text="Some job text")
    assert offer.title == "Backend"


def test_analyze_job_fetches_url_when_raw_text_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_analyzer,
        "fetch_job_text",
        lambda url: "We need a Python engineer with FastAPI.",
    )
    payload = (
        '{"title": "Python Dev", "company": "RemoteCo", "requirements": ["Python"], '
        '"nice_to_have": [], "responsibilities": [], "keywords": ["python"]}'
    )
    monkeypatch.setattr(job_analyzer, "get_json_llm", lambda: FakeLLM(payload))

    offer = job_analyzer.analyze_job(url="https://example.com/job", raw_text=None)

    assert offer.raw_text == "We need a Python engineer with FastAPI."
    assert offer.title == "Python Dev"


def test_analyze_job_parses_json_embedded_in_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = 'Here is the result: {"title": "Embedded", "company": "Y", "requirements": []} end.'
    monkeypatch.setattr(job_analyzer, "get_json_llm", lambda: FakeLLM(payload))
    offer = job_analyzer.analyze_job(url=None, raw_text="Job posting")
    assert offer.title == "Embedded"


def test_analyze_job_normalizes_scalar_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = '{"title": "Role", "company": "Z", "requirements": "Python"}'
    monkeypatch.setattr(job_analyzer, "get_json_llm", lambda: FakeLLM(payload))
    offer = job_analyzer.analyze_job(url=None, raw_text="Job posting")
    assert offer.requirements == ["Python"]
