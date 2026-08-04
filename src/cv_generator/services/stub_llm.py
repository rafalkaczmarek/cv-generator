"""Deterministic LLM stub for automated end-to-end tests.

Activated via ``LLM_PROVIDER=stub``. Returns canned JSON payloads that match the
sample profile used in Playwright flows (Jan Kowalski @ Acme Corp).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import Runnable

_JOB_OFFER_JSON = json.dumps(
    {
        "title": "Senior Python Engineer",
        "company": "GammaTech",
        "location": "Remote",
        "requirements": ["Python", "FastAPI", "PostgreSQL"],
        "nice_to_have": ["Docker"],
        "responsibilities": ["Design backend services"],
        "keywords": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    },
    ensure_ascii=False,
)

_TAILORED_CV_JSON_EN = json.dumps(
    {
        "headline": "Senior Python Engineer",
        "summary": "Backend engineer with Python, FastAPI and PostgreSQL experience.",
        "experiences": [
            {
                "company": "Acme Corp",
                "title": "Senior Backend Engineer",
                "date_range": "01/2021 - Present",
                "bullets": ["Built FastAPI services on Kubernetes."],
            }
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "courses": ["AWS Certified Developer"],
        "languages": ["Polish - native", "English - fluent"],
        "education_lines": ["MSc - Computer Science - Warsaw University of Technology"],
    },
    ensure_ascii=False,
)

_TAILORED_CV_JSON_PL = json.dumps(
    {
        "headline": "Starszy inżynier Python",
        "summary": "Inżynier backendu z doświadczeniem w Python, FastAPI i PostgreSQL.",
        "experiences": [
            {
                "company": "Acme Corp",
                "title": "Senior Backend Engineer",
                "date_range": "01/2021 - obecnie",
                "bullets": ["Budowałem usługi FastAPI na Kubernetes."],
            }
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "courses": ["AWS Certified Developer"],
        "languages": ["Polski - natywny", "Angielski - biegły"],
        "education_lines": ["mgr inż. - Informatyka - Politechnika Warszawska"],
    },
    ensure_ascii=False,
)


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


def _inputs_as_text(inputs: Any) -> str:
    if isinstance(inputs, str):
        return inputs
    if isinstance(inputs, dict):
        return json.dumps(inputs, ensure_ascii=False, default=str)
    if isinstance(inputs, list):
        return json.dumps(inputs, ensure_ascii=False, default=str)
    return str(inputs)


class StubLLM(Runnable[Any, _StubResponse]):
    """Returns job-offer or tailored-CV JSON based on prompt content."""

    def bind(self, **_kwargs: Any) -> StubLLM:
        return self

    def invoke(
        self,
        inputs: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> _StubResponse:
        text = _inputs_as_text(inputs)
        if "TailoredCV JSON" in text or "tailoring an existing profile" in text:
            if "Output language: pl" in text:
                return _StubResponse(_TAILORED_CV_JSON_PL)
            return _StubResponse(_TAILORED_CV_JSON_EN)
        return _StubResponse(_JOB_OFFER_JSON)


def get_stub_llm() -> StubLLM:
    return StubLLM()
