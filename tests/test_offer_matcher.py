"""Tests for the deterministic BoardOffer matcher."""

from __future__ import annotations

from datetime import datetime

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.offer_matcher import (
    score_offer,
    score_offers,
    sort_results,
    top_profile_keywords,
)


def _offer(**kwargs: object) -> BoardOffer:
    defaults: dict[str, object] = {
        "source": BoardSource.JUSTJOIN,
        "external_id": kwargs.get("external_id", "1"),
        "url": "https://example.com/offer/1",
        "title": "Python Dev",
    }
    defaults.update(kwargs)
    return BoardOffer(**defaults)  # type: ignore[arg-type]


def test_score_offer_returns_full_score_when_all_skills_present(sample_profile) -> None:
    offer = _offer(skills=["Python", "FastAPI"])
    result = score_offer(sample_profile, offer)
    assert result.match_score == 100
    assert set(result.matched) >= {"Python", "FastAPI"}
    assert result.missing == []


def test_score_offer_reports_missing_skills(sample_profile) -> None:
    offer = _offer(skills=["Python", "Rust", "Elixir"])
    result = score_offer(sample_profile, offer)
    assert "Python" in result.matched
    assert {"Rust", "Elixir"}.issubset(set(result.missing))
    assert 0 < result.match_score < 100


def test_score_offer_returns_zero_for_offer_without_skills(sample_profile) -> None:
    offer = _offer(skills=[])
    result = score_offer(sample_profile, offer)
    assert result.match_score == 0


def test_score_offers_filters_below_threshold(sample_profile) -> None:
    good = _offer(external_id="good", skills=["Python", "FastAPI"])
    bad = _offer(external_id="bad", skills=["Rust", "Elixir", "Haskell"])
    results = score_offers(sample_profile, [good, bad], min_score=50)
    keys = {r.offer.external_id for r in results}
    assert "good" in keys
    assert "bad" not in keys


def test_score_offers_filters_offers_without_skills(sample_profile) -> None:
    """Empty-skill offers score 0% and must not bypass the min-score filter."""
    orphan = _offer(external_id="orphan", skills=[])
    results = score_offers(sample_profile, [orphan], min_score=90)
    assert results == []


def test_score_offers_filters_zero_score_unmatched_skills(sample_profile) -> None:
    """Offers whose skills none match the profile score 0% and are dropped."""
    zero = _offer(external_id="zero", skills=["Erlang", "Haskell", "Cobol"])
    assert score_offer(sample_profile, zero).match_score == 0
    results = score_offers(sample_profile, [zero], min_score=40)
    assert results == []


def test_score_offers_hides_zero_percent_among_mixed_list(sample_profile) -> None:
    good = _offer(external_id="good", skills=["Python", "FastAPI"])
    skilless = _offer(external_id="skilless", skills=[])
    unmatched = _offer(external_id="unmatched", skills=["Erlang", "Haskell"])
    results = score_offers(
        sample_profile, [good, skilless, unmatched], min_score=40
    )
    assert [r.offer.external_id for r in results] == ["good"]
    assert all(r.match_score > 0 for r in results)


def test_score_offers_keeps_zero_score_when_threshold_is_zero(sample_profile) -> None:
    """Threshold 0 is an explicit 'show everything' opt-in, including 0%."""
    skilless = _offer(external_id="skilless", skills=[])
    unmatched = _offer(external_id="unmatched", skills=["Erlang"])
    results = score_offers(sample_profile, [skilless, unmatched], min_score=0)
    keys = {r.offer.external_id for r in results}
    assert keys == {"skilless", "unmatched"}
    assert all(r.match_score == 0 for r in results)


def test_sort_results_prefers_active_then_recent_then_score(sample_profile) -> None:
    older_high = _offer(
        external_id="old_high",
        published_at=datetime(2025, 1, 1),
        skills=["Python", "FastAPI"],
    )
    newer_low = _offer(
        external_id="new_low",
        published_at=datetime(2026, 1, 1),
        skills=["Python", "Rust", "Elixir"],
    )
    inactive_top = _offer(
        external_id="dead",
        published_at=datetime(2030, 1, 1),
        skills=["Python", "FastAPI"],
        is_active=False,
    )

    results = score_offers(
        sample_profile, [older_high, newer_low, inactive_top], min_score=0
    )
    sorted_results = sort_results(results)
    order = [r.offer.external_id for r in sorted_results]
    assert order[0] == "new_low"
    assert order[1] == "old_high"
    assert order[-1] == "dead"


def test_top_profile_keywords_deduplicates_and_limits(sample_profile) -> None:
    keywords = top_profile_keywords(sample_profile, limit=3)
    assert len(keywords) == 3
    assert len(keywords) == len({k.lower() for k in keywords})
