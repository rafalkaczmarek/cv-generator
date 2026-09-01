"""Tests for CVTailor with the LLM stubbed out."""

from __future__ import annotations

from datetime import date

import pytest

from cv_generator.agents import tailor
from cv_generator.models import Education, Experience, TailoredCV
from tests.fake_llm import FakeLLM


@pytest.fixture
def fake_tailor_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    payload = (
        '{"headline": "Senior Python Engineer", '
        '"summary": "Backend engineer with FastAPI and Kubernetes experience.", '
        '"experiences": [{"company": "Acme Corp", "title": "Senior Backend Engineer", '
        '"date_range": "01/2021 - obecnie", "bullets": ["Built FastAPI services."]}], '
        '"skills": ["Python", "FastAPI", "Kubernetes"], '
        '"courses": ["Kubernetes Fundamentals"], '
        '"languages": ["Polski - natywny"], '
        '"education_lines": ["mgr inż. - Informatyka - Politechnika Warszawska"]}'
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
    assert "Kubernetes Fundamentals" in cv.courses
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
        '"skills": "Python, FastAPI", "courses": "AWS Dev", '
        '"languages": "Polski", "education_lines": "Uni"}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.skills == ["Python, FastAPI"]
    assert cv.courses == ["AWS Dev"]
    assert cv.languages == ["Polski"]
    assert cv.education_lines == [
        "mgr inż., Informatyka — Politechnika Warszawska (2013 - 2018)"
    ]


def test_tailor_cv_falls_back_to_profile_courses(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"headline": "Dev", "summary": "Summary.", "experiences": [], "skills": ["Python"]}'
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.courses == sample_profile.courses


def test_tailor_cv_sets_language_and_present_label(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"headline": "Dev", "summary": "Summary.", "experiences": []}'
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(
        profile=sample_profile, job=sample_job, gap=sample_gap, language="en"
    )
    assert cv.language == "en"
    assert cv.experiences[0].date_range.endswith("Present")

    cv_pl = tailor.tailor_cv(
        profile=sample_profile, job=sample_job, gap=sample_gap, language="pl"
    )
    assert cv_pl.language == "pl"
    assert cv_pl.experiences[0].date_range.endswith("obecnie")


def test_tailor_cv_education_keeps_profile_degree(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": [], '
        '"education_lines": ["Politechnika Warszawska"]}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=sample_profile, job=sample_job, gap=sample_gap)
    assert cv.education_lines == [
        "mgr inż., Informatyka — Politechnika Warszawska (2013 - 2018)"
    ]


def test_tailor_cv_education_includes_full_degree_title(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    profile = sample_profile.model_copy(
        update={
            "education": [
                Education(
                    institution="Lodz University of Technology",
                    degree="Bachelor of Science in Computer Science",
                    start_date=date(2011, 1, 1),
                    end_date=date(2015, 1, 1),
                )
            ]
        }
    )
    payload = '{"headline": "Dev", "summary": "Summary.", "experiences": []}'
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=profile, job=sample_job, gap=sample_gap)
    assert cv.education_lines == [
        "Bachelor of Science in Computer Science — Lodz University of Technology "
        "(2011 - 2015)"
    ]


def test_rewrite_summary_returns_new_text(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"summary": "Alternative summary tailored to FastAPI roles."}'
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    summary = tailor.rewrite_summary(
        profile=sample_profile,
        job=sample_job,
        gap=sample_gap,
        current_summary="Old summary.",
        headline="Senior Python Engineer",
        language="en",
    )
    assert summary == "Alternative summary tailored to FastAPI roles."


def test_rewrite_summary_falls_back_to_current_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM('{"summary": ""}'))
    summary = tailor.rewrite_summary(
        profile=sample_profile,
        job=sample_job,
        gap=sample_gap,
        current_summary="Keep me.",
    )
    assert summary == "Keep me."


def test_rewrite_summary_uses_plain_llm_for_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    payload = '{"summary": "Anthropic rewrite."}'
    llm_stub = FakeLLM(payload)
    monkeypatch.setattr(tailor, "_supports_json_mode", lambda: False)
    monkeypatch.setattr(tailor, "get_llm", lambda: llm_stub)
    summary = tailor.rewrite_summary(
        profile=sample_profile,
        job=sample_job,
        gap=sample_gap,
        current_summary="Old.",
    )
    assert summary == "Anthropic rewrite."


def test_tailor_cv_fills_project_date_range_from_profile(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    profile = sample_profile.model_copy(
        update={
            "experiences": [
                *sample_profile.experiences,
                Experience(
                    company="Projekt",
                    title="Pekao website",
                    start_date=date(2019, 8, 1),
                    end_date=date(2020, 6, 1),
                ),
                Experience(
                    company="Projekt",
                    title="CV Generator",
                    start_date=date(2024, 1, 1),
                    is_current=True,
                ),
            ]
        }
    )
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": ['
        '{"company": "Acme Corp", "title": "Senior Backend Engineer", "bullets": ["API"]},'
        '{"company": "Projekt", "title": "Pekao website", "bullets": ["Frontend"]},'
        '{"company": "Projekt", "title": "CV Generator", "bullets": ["Generator"]}'
        "]}"
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(
        profile=profile, job=sample_job, gap=sample_gap, language="pl"
    )
    by_title = {exp.title: exp.date_range for exp in cv.experiences}
    assert by_title["Pekao website"] == "08/2019 - 06/2020"
    assert by_title["CV Generator"] == "01/2024 - obecnie"
    assert by_title["Senior Backend Engineer"] == "01/2021 - obecnie"
    pekao = next(exp for exp in cv.experiences if exp.title == "Pekao website")
    assert pekao.heading == "Pekao website"


def test_tailor_cv_formats_current_project_as_present_in_english(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    profile = sample_profile.model_copy(
        update={
            "experiences": [
                Experience(
                    company="Projekt",
                    title="CV Generator",
                    start_date=date(2024, 1, 1),
                    is_current=True,
                )
            ]
        }
    )
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": ['
        '{"company": "Projekt", "title": "CV Generator", "bullets": ["Generator"]}]}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(
        profile=profile, job=sample_job, gap=sample_gap, language="en"
    )
    assert cv.experiences[0].date_range == "01/2024 - Present"


def test_tailor_cv_keeps_llm_dates_when_profile_date_unknown(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    profile = sample_profile.model_copy(
        update={
            "experiences": [
                Experience(
                    company="Projekt",
                    title="Undated App",
                    start_date=date(1900, 1, 1),
                )
            ]
        }
    )
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": ['
        '{"company": "Projekt", "title": "Undated App", '
        '"date_range": "2018 - 2019", "bullets": ["Work"]}]}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=profile, job=sample_job, gap=sample_gap, language="en")
    assert cv.experiences[0].date_range == "2018 - 2019"


def test_tailor_cv_fills_project_dates_when_llm_company_differs(
    monkeypatch: pytest.MonkeyPatch,
    sample_profile,
    sample_job,
    sample_gap,
) -> None:
    profile = sample_profile.model_copy(
        update={
            "experiences": [
                *sample_profile.experiences,
                Experience(
                    company="Projekt",
                    title="Pekao website",
                    start_date=date(2019, 8, 1),
                    end_date=date(2020, 6, 1),
                ),
            ]
        }
    )
    payload = (
        '{"headline": "Dev", "summary": "Summary.", "experiences": ['
        '{"company": "Bank Pekao S.A.", "title": "Pekao website", '
        '"date_range": "", "bullets": ["Frontend"]}]}'
    )
    monkeypatch.setattr(tailor, "get_json_llm", lambda: FakeLLM(payload))
    cv = tailor.tailor_cv(profile=profile, job=sample_job, gap=sample_gap, language="en")
    assert cv.experiences[0].date_range == "08/2019 - 06/2020"
