"""Deterministic gap analysis between Profile and JobOffer.

No LLM here: fuzzy-matches skills and keywords and ranks experiences by overlap
with the job's keywords. The output guides the Tailor agent.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from cv_generator.graph.state import GapAnalysis
from cv_generator.models import JobOffer, Profile

_FUZZ_THRESHOLD = 80


def _normalize(value: str) -> str:
    return value.strip().lower()


def _profile_skill_pool(profile: Profile) -> list[str]:
    pool = list(profile.skills)
    for exp in profile.experiences:
        pool.extend(exp.technologies)
        pool.extend(exp.bullets)
        if exp.summary:
            pool.append(exp.summary)
    return [_normalize(p) for p in pool if p]


def _matches(needle: str, haystack: list[str]) -> bool:
    n = _normalize(needle)
    if not n:
        return False
    for hay in haystack:
        if n in hay:
            return True
        if fuzz.partial_ratio(n, hay) >= _FUZZ_THRESHOLD:
            return True
    return False


def analyze_gap(profile: Profile, job: JobOffer) -> GapAnalysis:
    pool = _profile_skill_pool(profile)

    job_signals = list(dict.fromkeys(job.keywords + job.requirements))
    matched: list[str] = []
    missing: list[str] = []
    for signal in job_signals:
        if _matches(signal, pool):
            matched.append(signal)
        else:
            missing.append(signal)

    relevant_indices: list[int] = []
    for idx, exp in enumerate(profile.experiences):
        exp_pool = [_normalize(t) for t in (*exp.technologies, *exp.bullets, exp.title, exp.summary or "")]
        if any(_matches(k, exp_pool) for k in job.keywords):
            relevant_indices.append(idx)

    notes = []
    if matched:
        notes.append(f"Emphasize matched skills first: {', '.join(matched[:8])}.")
    if missing:
        notes.append(
            "Do not invent the following missing skills; only mention if profile already implies them: "
            + ", ".join(missing[:8])
        )

    return GapAnalysis(
        matched_skills=matched,
        missing_skills=missing,
        relevant_experiences=relevant_indices,
        emphasis_notes=notes,
    )
