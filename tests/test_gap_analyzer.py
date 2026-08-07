from __future__ import annotations

from cv_generator.agents.gap_analyzer import analyze_gap
from cv_generator.models import JobOffer


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
    job = JobOffer(
        raw_text="Database role",
        requirements=["postgresql"],
        keywords=[],
    )
    gap = analyze_gap(sample_profile, job)
    matched = [m.lower() for m in gap["matched_skills"]]
    assert "postgresql" in matched


def test_gap_does_not_match_short_skill_as_letter_inside_other_words(
    sample_profile,
) -> None:
    """'C' must not match Docker/React/e-commerce via substring or fuzzy partial."""
    job = JobOffer(
        raw_text="Embedded C Developer",
        title="Embedded C Developer",
        requirements=["C", "Linux"],
        keywords=["C"],
    )
    gap = analyze_gap(sample_profile, job)
    matched_lower = {m.lower() for m in gap["matched_skills"]}
    missing_lower = {m.lower() for m in gap["missing_skills"]}
    assert "c" not in matched_lower
    assert "c" in missing_lower


def test_gap_matches_short_skill_when_present_as_own_token(sample_profile) -> None:
    profile = sample_profile.model_copy(
        update={"skills": [*sample_profile.skills, "C", "Embedded Linux"]}
    )
    job = JobOffer(
        raw_text="Embedded C role",
        requirements=["C"],
        keywords=[],
    )
    gap = analyze_gap(profile, job)
    assert "C" in gap["matched_skills"]


def test_gap_does_not_treat_cplusplus_as_plain_c(sample_profile) -> None:
    profile = sample_profile.model_copy(update={"skills": ["C++", "Python"]})
    job = JobOffer(raw_text="C developer", requirements=["C"], keywords=[])
    gap = analyze_gap(profile, job)
    assert "C" in gap["missing_skills"]
    assert "C" not in gap["matched_skills"]
