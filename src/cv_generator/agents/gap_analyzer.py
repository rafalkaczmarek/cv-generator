"""Deterministic gap analysis between Profile and JobOffer.

No LLM here: fuzzy-matches skills and keywords and ranks experiences by overlap
with the job's keywords. The output guides the Tailor agent.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from cv_generator.graph.state import GapAnalysis
from cv_generator.models import JobOffer, Profile

_FUZZ_THRESHOLD = 80
# Single-/two-letter skills (C, R, Go) must not match as letters inside other words.
_SHORT_SKILL_MAX_LEN = 2
# Keep compounds like C++, C#, Objective-C, Node.js, CI/CD as single tokens.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[+#]+|[-./][a-z0-9]+)*", re.IGNORECASE)


def _normalize(value: str) -> str:
    return value.strip().lower()


def _tokens(value: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(value)]


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
    if len(n) <= _SHORT_SKILL_MAX_LEN:
        return any(n in _tokens(hay) for hay in haystack)
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
