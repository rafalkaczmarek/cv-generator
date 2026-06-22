"""QualityValidator — deterministic scoring of a TailoredCV against a JobOffer.

Two responsibilities:
1. Detect hallucinations: company names or technology keywords appearing in the
   tailored CV but absent from the original profile.
2. Score keyword coverage and produce actionable feedback for another tailoring pass.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from cv_generator.models import JobOffer, Profile, TailoredCV

_FUZZ_THRESHOLD = 85


def _norm(value: str) -> str:
    return value.strip().lower()


def _profile_tokens(profile: Profile) -> set[str]:
    tokens: set[str] = set()
    for exp in profile.experiences:
        tokens.add(_norm(exp.company))
        tokens.add(_norm(exp.title))
        tokens.update(_norm(t) for t in exp.technologies)
        tokens.update(_norm(b) for b in exp.bullets)
        if exp.summary:
            tokens.add(_norm(exp.summary))
    tokens.update(_norm(s) for s in profile.skills)
    if profile.summary:
        tokens.add(_norm(profile.summary))
    if profile.headline:
        tokens.add(_norm(profile.headline))
    return {t for t in tokens if t}


def _contains(needle: str, haystack: set[str]) -> bool:
    n = _norm(needle)
    if not n:
        return False
    for hay in haystack:
        if n in hay or fuzz.partial_ratio(n, hay) >= _FUZZ_THRESHOLD:
            return True
    return False


def validate(*, profile: Profile, job: JobOffer, cv: TailoredCV) -> tuple[int, str, TailoredCV]:
    """Return (score 0-100, feedback for next iteration, CV with score metadata)."""
    profile_pool = _profile_tokens(profile)

    cv_text_pool: set[str] = {_norm(cv.headline), _norm(cv.summary)}
    for exp in cv.experiences:
        cv_text_pool.add(_norm(exp.company))
        cv_text_pool.add(_norm(exp.title))
        cv_text_pool.update(_norm(b) for b in exp.bullets)
    cv_text_pool.update(_norm(s) for s in cv.skills)
    cv_text_pool.discard("")

    job_signals = list(dict.fromkeys(job.keywords + job.requirements))
    matched = [k for k in job_signals if _contains(k, cv_text_pool)]
    missing = [k for k in job_signals if k not in matched]

    coverage = (len(matched) / len(job_signals)) if job_signals else 1.0
    score = int(round(coverage * 100))

    hallucinations: list[str] = []
    profile_companies = {_norm(e.company) for e in profile.experiences}
    for exp in cv.experiences:
        if _norm(exp.company) and _norm(exp.company) not in profile_companies:
            hallucinations.append(f"company '{exp.company}'")
    for skill in cv.skills:
        if not _contains(skill, profile_pool):
            hallucinations.append(f"skill '{skill}'")

    if hallucinations:
        score = max(0, score - 25)

    feedback_lines: list[str] = []
    if missing:
        feedback_lines.append(
            "Cover these job keywords if the profile supports them: " + ", ".join(missing[:10])
        )
    if hallucinations:
        feedback_lines.append(
            "Remove or replace fabricated items not present in profile: "
            + "; ".join(hallucinations[:8])
        )
    if not feedback_lines:
        feedback_lines.append("Looks good. No issues detected.")

    cv = cv.model_copy(
        update={
            "matched_keywords": matched,
            "missing_keywords": missing,
            "match_score": score,
        }
    )

    return score, "\n".join(feedback_lines), cv
