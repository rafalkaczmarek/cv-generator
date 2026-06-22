"""Tests for JobAnalyzer with the LLM stubbed out."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import Runnable

from cv_generator.agents import job_analyzer


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM(Runnable[Any, _FakeLLMResponse]):
    def __init__(self, payload: str) -> None:
        super().__init__()
        self.payload = payload

    def bind(self, **_kwargs: Any) -> _FakeLLM:
        return self

    def invoke(
        self,
        _inputs: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> _FakeLLMResponse:
        return _FakeLLMResponse(self.payload)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    payload = (
        '{"title": "Senior Python Engineer", "company": "GammaTech", '
        '"location": "Remote", "requirements": ["Python", "FastAPI"], '
        '"nice_to_have": ["Terraform"], "responsibilities": ["Design APIs"], '
        '"keywords": ["python", "fastapi", "kubernetes"]}'
    )
    llm = _FakeLLM(payload)

    def _factory():
        return llm

    monkeypatch.setattr(job_analyzer, "get_llm", _factory)
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
    monkeypatch.setattr(job_analyzer, "get_llm", lambda: _FakeLLM(fenced))
    offer = job_analyzer.analyze_job(url=None, raw_text="Some job text")
    assert offer.title == "Backend"
