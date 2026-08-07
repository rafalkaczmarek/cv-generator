"""Score BoardOffers against a Profile without invoking any LLM.

Reuses the deterministic :func:`analyze_gap` logic by wrapping a
``BoardOffer`` into a lightweight ``JobOffer`` (its ``skills`` become the
``requirements``/``keywords`` the gap analyzer scores against).
"""

from __future__ import annotations

from dataclasses import dataclass

from cv_generator.agents.gap_analyzer import analyze_gap
from cv_generator.config import get_settings
from cv_generator.models import BoardOffer, JobOffer, Profile


@dataclass(frozen=True)
class MatchResult:
    """Score of a single ``BoardOffer`` against a ``Profile``."""

    offer: BoardOffer
    match_score: int
    matched: list[str]
    missing: list[str]


def score_offer(profile: Profile, offer: BoardOffer) -> MatchResult:
    """Compute the match score for a single board offer."""
    keywords = _offer_keywords(offer)
    fake_job = JobOffer(
        raw_text=offer.description_snippet or offer.title or "",
        title=offer.title,
        company=offer.company,
        location=offer.location,
        requirements=keywords,
        keywords=keywords,
    )
    gap = analyze_gap(profile, fake_job)
    matched = list(gap.get("matched_skills", []))
    missing = list(gap.get("missing_skills", []))
    total = len(matched) + len(missing)
    score = round(100 * len(matched) / total) if total else 0
    return MatchResult(offer=offer, match_score=score, matched=matched, missing=missing)


def score_offers(
    profile: Profile,
    offers: list[BoardOffer],
    *,
    min_score: int | None = None,
) -> list[MatchResult]:
    """Score every offer and drop those below the configured threshold.

    Offers with no declared skills (``requirements`` and ``keywords`` empty)
    are returned with a neutral 0 score and pass the filter — they cannot be
    scored, so we surface them for the user to decide.
    """
    threshold = min_score if min_score is not None else get_settings().min_board_match_score
    results: list[MatchResult] = []
    for offer in offers:
        result = score_offer(profile, offer)
        has_signals = bool(_offer_keywords(offer))
        if not has_signals or result.match_score >= threshold:
            results.append(result)
    return results


def sort_results(results: list[MatchResult]) -> list[MatchResult]:
    """Freshest first, then best-matching, with active offers before inactive."""
    return sorted(
        results,
        key=lambda r: (
            r.offer.is_active,
            r.offer.published_at.timestamp() if r.offer.published_at else 0.0,
            r.match_score,
        ),
        reverse=True,
    )


def _offer_keywords(offer: BoardOffer) -> list[str]:
    """Unique, order-preserving list of tokens describing what the offer wants."""
    tokens = [t.strip() for t in offer.skills if t and t.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(token)
    return unique


def top_profile_keywords(profile: Profile, *, limit: int | None = None) -> list[str]:
    """Pick the most useful skills from a profile for board search queries."""
    limit = limit or get_settings().board_query_top_skills
    seen: set[str] = set()
    keywords: list[str] = []
    for source in (profile.skills, *(exp.technologies for exp in profile.experiences)):
        for skill in source:
            key = skill.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            keywords.append(skill.strip())
            if len(keywords) >= limit:
                return keywords
    return keywords


__all__ = ["MatchResult", "score_offer", "score_offers", "sort_results", "top_profile_keywords"]
