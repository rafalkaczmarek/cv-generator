"""Tests for CVTailor with the LLM stubbed out."""

from __future__ import annotations

import pytest

from cv_generator.agents import tailor
from cv_generator.models import TailoredCV
from tests.fake_llm import FakeLLM


@pytest.fixture
def fake_tailor_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    payload = (
        '{"headline": "Senior Python Engineer", '
        '"summary": "Backend engineer with FastAPI and Kubernetes experience.", '
        '"experiences": [{"company": "Acme Corp", "title": "Senior Backend Engineer", '
        '"date_range": "01/2021 - obecnie", "bullets": ["Built FastAPI services."]}], '
        '"skills": ["Python", "FastAPI", "Kubernetes"], '
        '"languages": ["Polski - natywny"], '
        '"education_lines": ["mgr inż. - Informatyka - Politechnika Warszawska"], '
        '"certifications": []}'
    )
    llm = FakeLLM(payload)
    monkeypatch.setattr(tailor, "get_json_llm", lambda: llm)
    return llm


def test_tailor_cv_builds_from_llm_json(
    fake_tailor_llm,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert isinstance(cv, TailoredCV)
    assert cv.headline == "Senior Python Engineer"
    assert cv.full_name == sample_profile.full_name
    assert "FastAPI" in cv.skills
    assert cv.experiences[0].company == "Acme Corp"


def test_tailor_cv_falls_back_to_profile_experiences(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"headline": "Dev", "summary": "Summary.", "experiences": []}'
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.experiences
    assert cv.experiences[0].company == sample_profile.sorted_experiences()[0].company


def test_tailor_cv_handles_markdown_fenced_json(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    fenced = (
        '```json\n{"headline": "Backend Lead", "summary": "Lead dev.", '
        '"experiences": [], "skills": ["Python"]}\n```'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(fenced))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.headline == "Backend Lead"


def test_tailor_cv_uses_plain_llm_for_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"headline": "Anthropic CV", "summary": "Done.", "experiences": []}'
    llm_stub = FakeLLM(payload)
    monkeypatch.setattr(tailor, "_supports_json_mode", lambda: False)
    monkeypatch.setattr(tailor, "get_llm", lambda: llm_stub)

    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.headline == "Anthropic CV"


def test_tailor_cv_skips_invalid_experience_entries(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = (
        '{"headline": "Dev", "summary": "Summary.", '
        '"experiences": ["not-a-dict", {"company": "Acme Corp", "title": "Engineer", '
        '"date_range": "2021-2022", "bullets": ["Did work"]}]}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert len(cv.experiences) == 1
    assert cv.experiences[0].company == "Acme Corp"


def test_tailor_cv_normalizes_string_list_fields(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": [], '
        '"skills": "Python, FastAPI", "languages": "Polski", "education_lines": "Uni"}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.skills == ["Python, FastAPI"]
    assert cv.languages == ["Polski"]
    assert cv.education_lines == ["Uni"]
