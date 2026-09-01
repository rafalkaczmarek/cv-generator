"""Tests for the LangGraph CV generation pipeline."""

from __future__ import annotations

from pathlib import Path

from docx import Document

from cv_generator.graph import pipeline
from cv_generator.graph.pipeline import generate_cv
from cv_generator.graph.state import GapAnalysis
from cv_generator.models import TailoredCV
from cv_generator.services.docx_generator import render_cv
from cv_generator.services.linkedin_import import profile_from_linkedin_zip
from tests.e2e.fixtures_data import E2E_PROJECT_DATE_RANGES_EN, build_linkedin_zip


def test_generate_cv_completes_when_score_sufficient(
    monkeypatch,
    sample_profile,
    sample_job,
    sample_tailored_cv,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "analyze_gap",
        lambda _profile, _job: GapAnalysis(emphasis_notes=[]),
    )
    monkeypatch.setattr(pipeline, "tailor_cv", lambda **kwargs: sample_tailored_cv)
    monkeypatch.setattr(
        pipeline,
        "validate",
        lambda **kwargs: (85, "Looks good.", kwargs["cv"]),
    )

    result = pipeline.generate_cv(sample_profile, sample_job)

    assert isinstance(result, TailoredCV)
    assert result.full_name == sample_tailored_cv.full_name


def test_generate_cv_retries_until_max_iterations(
    monkeypatch,
    sample_profile,
    sample_job,
    sample_tailored_cv,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "analyze_gap",
        lambda _profile, _job: GapAnalysis(emphasis_notes=[]),
    )

    tailor_calls = 0

    def fake_tailor(**kwargs) -> TailoredCV:
        nonlocal tailor_calls
        tailor_calls += 1
        return sample_tailored_cv

    monkeypatch.setattr(pipeline, "tailor_cv", fake_tailor)
    monkeypatch.setattr(
        pipeline,
        "validate",
        lambda **kwargs: (40, "Needs work.", kwargs["cv"]),
    )

    result = pipeline.generate_cv(sample_profile, sample_job)

    assert result is sample_tailored_cv
    assert tailor_calls == 2


def test_generate_cv_passes_language_to_tailor(
    monkeypatch,
    sample_profile,
    sample_job,
    sample_tailored_cv,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "analyze_gap",
        lambda _profile, _job: GapAnalysis(emphasis_notes=[]),
    )
    seen: dict[str, str] = {}

    def fake_tailor(**kwargs) -> TailoredCV:
        seen["language"] = kwargs["language"]
        return sample_tailored_cv

    monkeypatch.setattr(pipeline, "tailor_cv", fake_tailor)
    monkeypatch.setattr(
        pipeline,
        "validate",
        lambda **kwargs: (90, "ok", kwargs["cv"]),
    )

    pipeline.generate_cv(sample_profile, sample_job, language="pl")
    assert seen["language"] == "pl"


def test_generate_cv_fills_project_dates_from_linkedin_zip(
    monkeypatch, sample_job, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    zip_path = build_linkedin_zip(tmp_path / "export.zip")
    profile = profile_from_linkedin_zip(zip_path)
    cv = generate_cv(profile, sample_job, language="en")

    by_title = {exp.title: exp for exp in cv.experiences}
    for title, date_range in E2E_PROJECT_DATE_RANGES_EN.items():
        assert by_title[title].date_range == date_range
        assert by_title[title].heading == title
        assert by_title[title].company == "Projekt"

    path = render_cv(cv, template_id="cv_template.docx", filename="cv_projects.docx")
    text = "\n".join(p.text for p in Document(path).paragraphs)
    for title, date_range in E2E_PROJECT_DATE_RANGES_EN.items():
        assert title in text
        assert date_range in text
        assert f"{title} — Projekt" not in text