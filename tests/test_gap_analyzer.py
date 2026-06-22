from __future__ import annotations

from cv_generator.agents.gap_analyzer import analyze_gap


def test_gap_matches_known_skills(sample_profile, sample_job) -> None:
    gap = analyze_gap(sample_profile, sample_job)
    matched = [m.lower() for m in gap["matched_skills"]]
    assert "python" in matched
    assert "fastapi" in matched
    assert "kubernetes" in matched


def test_gap_flags_missing_skills(sample_profile, sample_job) -> None:
    gap = analyze_gap(sample_profile, sample_job)
    missing_lower = [m.lower() for m in gap["missing_skills"]]
    assert "terraform" in missing_lower


def test_gap_identifies_relevant_experiences(sample_profile, sample_job) -> None:
    gap = analyze_gap(sample_profile, sample_job)
    assert 0 in gap["relevant_experiences"]


def test_gap_fuzzy_matches_similar_skill_names(sample_profile) -> None:
    from cv_generator.models import JobOffer

    job = JobOffer(
        raw_text="Database role",
        requirements=["postgresql"],
        keywords=[],
    )
    gap = analyze_gap(sample_profile, job)
    matched = [m.lower() for m in gap["matched_skills"]]
    assert "postgresql" in matched
