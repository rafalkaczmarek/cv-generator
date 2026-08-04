"""Unit tests for preview-tab match-score reevaluation."""

from __future__ import annotations

from cv_generator.models import JobOffer, Profile, TailoredCV
from cv_generator.ui.preview import reevaluate_match_score


def test_reevaluate_requires_profile(sample_job: JobOffer, sample_tailored_cv: TailoredCV) -> None:
    updated, error = reevaluate_match_score(
        profile=None, job=sample_job, cv=sample_tailored_cv
    )
    assert updated is None
    assert error is not None
    assert "profilu" in error.lower()


def test_reevaluate_requires_job(
    sample_profile: Profile, sample_tailored_cv: TailoredCV
) -> None:
    updated, error = reevaluate_match_score(
        profile=sample_profile, job=None, cv=sample_tailored_cv
    )
    assert updated is None
    assert error is not None
    assert "oferty" in error.lower()


def test_reevaluate_updates_score_after_cv_edits(
    sample_profile: Profile, sample_job: JobOffer, sample_tailored_cv: TailoredCV
) -> None:
    baseline, baseline_error = reevaluate_match_score(
        profile=sample_profile, job=sample_job, cv=sample_tailored_cv
    )
    assert baseline_error is None
    assert baseline is not None
    assert baseline.match_score > 0

    stripped = sample_tailored_cv.model_copy(
        update={
            "headline": "Engineer",
            "summary": "General backend work.",
            "skills": ["Python"],
            "courses": [],
            "experiences": [
                exp.model_copy(update={"bullets": ["Built internal tools."]})
                for exp in sample_tailored_cv.experiences
            ],
            "match_score": 100,
            "matched_keywords": [],
            "missing_keywords": [],
        }
    )
    updated, error = reevaluate_match_score(
        profile=sample_profile, job=sample_job, cv=stripped
    )
    assert error is None
    assert updated is not None
    assert updated.match_score < baseline.match_score
    assert updated.missing_keywords
    assert any(k.lower() != "python" for k in updated.missing_keywords)


def test_reevaluate_refreshes_matched_keywords(
    sample_profile: Profile, sample_job: JobOffer, sample_tailored_cv: TailoredCV
) -> None:
    job = sample_job.model_copy(
        update={"keywords": ["Python", "FastAPI"], "requirements": ["Python"]}
    )
    weak = sample_tailored_cv.model_copy(
        update={
            "headline": "Engineer",
            "summary": "Backend.",
            "skills": ["Python"],
            "courses": [],
            "experiences": [
                exp.model_copy(update={"bullets": ["Shipped features."]})
                for exp in sample_tailored_cv.experiences
            ],
            "match_score": 0,
            "matched_keywords": [],
            "missing_keywords": ["Python", "FastAPI"],
        }
    )
    improved = weak.model_copy(
        update={
            "skills": ["Python", "FastAPI"],
            "summary": "Backend engineer with FastAPI experience.",
        }
    )
    updated, error = reevaluate_match_score(
        profile=sample_profile, job=job, cv=improved
    )
    assert error is None
    assert updated is not None
    assert updated.match_score == 100
    assert "FastAPI" in updated.matched_keywords
    assert updated.missing_keywords == []
