"""Deterministic LLM stub for automated end-to-end tests.

Activated via ``LLM_PROVIDER=stub``. Returns canned JSON payloads that match the
sample profile used in Playwright flows (Jan Kowalski @ Acme Corp).

When the tailor prompt includes a profile, experiences are echoed back so ZIP
imports keep projects. ``date_range`` is omitted for ``Projekt``/``Project``
entries to reproduce the production LLM skipping project dates.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import Runnable

_PROJECT_COMPANIES = frozenset({"projekt", "project"})
_PROFILE_MARKER = "Candidate profile (source of truth):"

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

_SUMMARY_JSON_EN = json.dumps(
    {
        "summary": (
            "Results-driven backend engineer focused on Python APIs, "
            "FastAPI services and reliable PostgreSQL data layers."
        )
    },
    ensure_ascii=False,
)

_SUMMARY_JSON_PL = json.dumps(
    {
        "summary": (
            "Inżynier backendu nastawiony na wyniki: API w Pythonie, "
            "usługi FastAPI oraz niezawodne warstwy danych w PostgreSQL."
        )
    },
    ensure_ascii=False,
)


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


def _inputs_as_text(inputs: Any) -> str:
    if isinstance(inputs, str):
        return inputs
    if hasattr(inputs, "to_string"):
        return str(inputs.to_string())
    if isinstance(inputs, dict):
        return json.dumps(inputs, ensure_ascii=False, default=str)
    if isinstance(inputs, list):
        parts: list[str] = []
        for item in inputs:
            content = getattr(item, "content", None)
            parts.append(content if isinstance(content, str) else str(item))
        return "\n".join(parts)
    return str(inputs)


def _profile_from_prompt(inputs: Any, text: str) -> dict[str, Any] | None:
    if isinstance(inputs, dict) and inputs.get("profile_json"):
        raw = inputs["profile_json"]
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
    idx = text.find(_PROFILE_MARKER)
    if idx < 0:
        return None
    rest = text[idx + len(_PROFILE_MARKER) :].lstrip()
    try:
        payload, _end = json.JSONDecoder().raw_decode(rest)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _experiences_omitting_project_dates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Copy profile experiences; leave project ``date_range`` empty like a real LLM."""
    out: list[dict[str, Any]] = []
    for exp in profile.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        company = str(exp.get("company") or "")
        item: dict[str, Any] = {
            "company": company,
            "title": str(exp.get("title") or ""),
            "location": exp.get("location"),
            "bullets": list(exp.get("bullets") or []),
        }
        if company.strip().casefold() not in _PROJECT_COMPANIES:
            item["date_range"] = "01/2021 - Present"
        out.append(item)
    return out


def _tailored_cv_json(inputs: Any, text: str) -> str:
    polish = "Output language: pl" in text
    canned = json.loads(_TAILORED_CV_JSON_PL if polish else _TAILORED_CV_JSON_EN)
    profile = _profile_from_prompt(inputs, text)
    if profile:
        echoed = _experiences_omitting_project_dates(profile)
        if echoed:
            canned["experiences"] = echoed
    return json.dumps(canned, ensure_ascii=False)


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
        if "rewriting only the professional summary" in text:
            if "Output language: pl" in text:
                return _StubResponse(_SUMMARY_JSON_PL)
            return _StubResponse(_SUMMARY_JSON_EN)
        if "TailoredCV JSON" in text or "tailoring an existing profile" in text:
            return _StubResponse(_tailored_cv_json(inputs, text))
        return _StubResponse(_JOB_OFFER_JSON)


def get_stub_llm() -> StubLLM:
    return StubLLM()
