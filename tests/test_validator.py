from __future__ import annotations

from cv_generator.agents.validator import validate
from cv_generator.models import TailoredExperience


def test_validator_scores_well_matched_cv(sample_profile, sample_job, sample_tailored_cv) -> None:
    score, feedback, cv = validate(profile=sample_profile, job=sample_job, cv=sample_tailored_cv)
    assert score >= 60
    assert cv.matched_keywords
    assert isinstance(feedback, str)


def test_validator_penalizes_hallucinated_company(sample_profile, sample_job, sample_tailored_cv) -> None:
    bad_cv = sample_tailored_cv.model_copy(
        update={
            "experiences": [
                TailoredExperience(
                    company="FakeCo That Does Not Exist",
                    title="Lead",
                    date_range="2024-2025",
                    bullets=["..."],
                )
            ]
        }
    )
    score, feedback, _ = validate(profile=sample_profile, job=sample_job, cv=bad_cv)
    assert "fabricated" in feedback.lower() or "remove" in feedback.lower()
    assert score < sample_tailored_cv.match_score + 100  # sanity bound


def test_validator_flags_invented_skills(sample_profile, sample_job, sample_tailored_cv) -> None:
    bad_cv = sample_tailored_cv.model_copy(
        update={"skills": ["Python", "QuantumBlockchainAI"]}
    )
    _, feedback, _ = validate(profile=sample_profile, job=sample_job, cv=bad_cv)
    assert "quantum" in feedback.lower() or "fabricated" in feedback.lower()


def test_validator_reports_no_issues_for_fully_covered_job(
    sample_profile, sample_job, sample_tailored_cv
) -> None:
    job = sample_job.model_copy(update={"keywords": ["Python", "FastAPI"], "requirements": ["Python"]})
    score, feedback, cv = validate(profile=sample_profile, job=job, cv=sample_tailored_cv)
    assert score >= 80
    assert "no issues" in feedback.lower() or "looks good" in feedback.lower()
    assert cv.match_score == score
