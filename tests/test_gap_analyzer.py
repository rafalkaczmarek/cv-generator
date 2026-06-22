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
