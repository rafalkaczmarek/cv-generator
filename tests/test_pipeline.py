"""Tests for the LangGraph CV generation pipeline."""

from __future__ import annotations

from cv_generator.graph import pipeline
from cv_generator.graph.state import GapAnalysis
from cv_generator.models import TailoredCV


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
