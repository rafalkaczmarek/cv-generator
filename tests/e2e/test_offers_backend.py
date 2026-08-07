"""In-process end-to-end coverage for the Polish job boards flow.

Streamlit runs in a subprocess so ``pytest-cov`` cannot attribute the UI-driven
paths. These tests replay the same happy path programmatically to keep
``cv-generator-e2e-cov`` meaningful and to catch integration regressions in the
board fetcher / matcher / CV generation chain.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cv_generator.agents.job_analyzer import analyze_job
from cv_generator.graph.pipeline import generate_cv
from cv_generator.models import BoardOffer, BoardSource, Profile
from cv_generator.services.boards import BoardFetchService, BoardQuery
from cv_generator.services.boards.base import BoardClientError
from cv_generator.services.docx_generator import render_cv
from cv_generator.services.offer_matcher import (
    score_offer,
    score_offers,
    sort_results,
    top_profile_keywords,
)
from cv_generator.services.storage import Storage

pytestmark = pytest.mark.e2e


@pytest.fixture
def e2e_profile() -> Profile:
    return Profile.model_validate(
        {
            "full_name": "Jan Kowalski",
            "headline": "Senior Python Developer",
            "email": "jan@example.com",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "courses": ["AWS Certified Developer", "Kubernetes Fundamentals"],
            "experiences": [
                {
                    "company": "Acme Corp",
                    "title": "Senior Backend Engineer",
                    "start_date": "2021-01-01",
                    "is_current": True,
                    "bullets": ["Built FastAPI services on Kubernetes."],
                    "technologies": ["Python", "FastAPI", "Kubernetes"],
                }
            ],
        }
    )


class _FakeBoardClient:
    """Stand-in for portal clients — returns a canned list of offers."""

    def __init__(self, source: BoardSource, offers: list[BoardOffer]) -> None:
        self.source = source
        self._offers = offers

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        _ = query
        return list(self._offers)


class _FailingBoardClient:
    def __init__(self, source: BoardSource, message: str) -> None:
        self.source = source
        self._message = message

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        _ = query
        raise BoardClientError(self._message)


def _make_offer(
    source: BoardSource,
    external_id: str,
    *,
    title: str = "Senior Python Engineer",
    company: str = "GammaTech",
    skills: list[str] | None = None,
    published_at: datetime | None = None,
) -> BoardOffer:
    return BoardOffer(
        source=source,
        external_id=external_id,
        url=f"https://example.com/{source.value}/{external_id}",
        title=title,
        company=company,
        skills=["Python", "FastAPI"] if skills is None else skills,
        published_at=published_at or datetime(2026, 8, 1),
    )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("APP_TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("CV_GENERATOR_IGNORE_ENV_FILE", "1")


def test_full_board_to_cv_flow_records_cv_bound_to_offer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    e2e_profile: Profile,
) -> None:
    """Refresh → score → generate CV → confirm the CV is bound to the offer."""
    _isolate(monkeypatch, tmp_path)

    storage = Storage()
    offer = _make_offer(BoardSource.JUSTJOIN, "e2e-1")
    service = BoardFetchService(
        storage=storage,
        clients={BoardSource.JUSTJOIN: _FakeBoardClient(BoardSource.JUSTJOIN, [offer])},
    )

    result = service.refresh(query=BoardQuery(keywords=["Python"]))
    assert result.fetched[BoardSource.JUSTJOIN] == 1
    assert not result.any_errors

    listed = storage.list_board_offers(sources=[BoardSource.JUSTJOIN])
    assert [o.offer_key for o in listed] == [offer.offer_key]

    match = score_offer(e2e_profile, listed[0])
    assert match.match_score >= 90
    storage.save_match(
        profile_name=e2e_profile.full_name,
        offer_key=match.offer.offer_key,
        match_score=match.match_score,
        matched=match.matched,
        missing=match.missing,
    )

    job = analyze_job(url=None, raw_text=f"{offer.title} at {offer.company}.")
    cv = generate_cv(e2e_profile, job)
    cv_path = render_cv(cv, filename=f"cv_{offer.offer_key.replace(':', '_')}.docx")
    assert cv_path.exists() and cv_path.stat().st_size > 0

    storage.record_generated_cv(
        profile_name=e2e_profile.full_name,
        job_slug=job.slug(),
        file_path=cv_path,
        cv=cv,
        offer_key=offer.offer_key,
    )

    found = storage.find_cv_for_offer(
        profile_name=e2e_profile.full_name, offer_key=offer.offer_key
    )
    assert found is not None
    assert found["offer_key"] == offer.offer_key
    assert Path(str(found["file_path"])) == cv_path


def test_refresh_marks_stale_offers_inactive_across_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    storage = Storage()

    first_run = {
        BoardSource.JUSTJOIN: _FakeBoardClient(
            BoardSource.JUSTJOIN,
            [
                _make_offer(BoardSource.JUSTJOIN, "a"),
                _make_offer(BoardSource.JUSTJOIN, "b"),
            ],
        ),
        BoardSource.NOFLUFF: _FakeBoardClient(
            BoardSource.NOFLUFF, [_make_offer(BoardSource.NOFLUFF, "n1")]
        ),
    }
    BoardFetchService(storage=storage, clients=first_run).refresh()

    # Second run: JJIT loses "b"; NoFluff drops out entirely.
    second_run = {
        BoardSource.JUSTJOIN: _FakeBoardClient(
            BoardSource.JUSTJOIN, [_make_offer(BoardSource.JUSTJOIN, "a")]
        ),
        BoardSource.NOFLUFF: _FailingBoardClient(BoardSource.NOFLUFF, "outage"),
    }
    result = BoardFetchService(storage=storage, clients=second_run).refresh()

    assert result.errors.get(BoardSource.NOFLUFF) == "outage"

    by_key = {o.offer_key: o for o in storage.list_board_offers()}
    assert by_key["justjoin:a"].is_active is True
    assert by_key["justjoin:b"].is_active is False
    # NoFluff outage should NOT wipe previously known active offers.
    assert by_key["nofluff:n1"].is_active is True


def test_matcher_orders_offers_and_respects_min_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    e2e_profile: Profile,
) -> None:
    _isolate(monkeypatch, tmp_path)

    good_recent = _make_offer(
        BoardSource.JUSTJOIN,
        "recent",
        skills=["Python", "FastAPI"],
        published_at=datetime(2026, 8, 1),
    )
    good_old = _make_offer(
        BoardSource.BULLDOGJOB,
        "old",
        skills=["Python", "FastAPI"],
        published_at=datetime(2024, 1, 1),
    )
    bad = _make_offer(
        BoardSource.NOFLUFF,
        "bad",
        skills=["Erlang", "Haskell", "Rust"],
        published_at=datetime(2026, 8, 5),
    )

    results = score_offers(
        e2e_profile,
        [good_old, bad, good_recent],
        min_score=60,
    )
    keys = [r.offer.external_id for r in sort_results(results)]

    assert "bad" not in keys
    assert keys[0] == "recent"
    assert keys[-1] == "old"


def test_matcher_hides_zero_percent_and_skillless_offers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    e2e_profile: Profile,
) -> None:
    """Regression: 0% offers (no skills or no overlap) must not pass the filter."""
    _isolate(monkeypatch, tmp_path)

    good = _make_offer(
        BoardSource.JUSTJOIN,
        "good",
        skills=["Python", "FastAPI"],
    )
    skilless = _make_offer(
        BoardSource.PRACUJ,
        "skilless",
        title="Mystery Role",
        skills=[],
    )
    zero_match = _make_offer(
        BoardSource.NOFLUFF,
        "zero",
        title="Erlang Guru",
        skills=["Erlang", "Haskell", "Cobol"],
    )

    assert score_offer(e2e_profile, skilless).match_score == 0
    assert score_offer(e2e_profile, zero_match).match_score == 0

    results = score_offers(
        e2e_profile,
        [good, skilless, zero_match],
        min_score=40,
    )
    keys = {r.offer.external_id for r in results}
    assert keys == {"good"}
    assert all(r.match_score > 0 for r in results)


def test_top_profile_keywords_seeds_query_from_profile_skills(
    e2e_profile: Profile,
) -> None:
    keywords = top_profile_keywords(e2e_profile, limit=3)
    assert len(keywords) == 3
    assert "Python" in keywords
