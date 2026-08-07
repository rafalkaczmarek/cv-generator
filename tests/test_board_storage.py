"""Board offer / match persistence in SQLite storage."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.storage import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """Fresh Storage per test — dodges shared `./data/cv_generator.sqlite`."""
    return Storage(db_path=tmp_path / "test.sqlite")


def _make_offer(
    source: BoardSource,
    external_id: str,
    *,
    title: str = "Dev",
    published_at: datetime | None = None,
) -> BoardOffer:
    return BoardOffer(
        source=source,
        external_id=external_id,
        url=f"https://example.com/{source.value}/{external_id}",
        title=title,
        skills=["Python", "FastAPI"],
        published_at=published_at,
    )


def test_upsert_and_list_board_offers_roundtrip(storage: Storage) -> None:
    offers = [
        _make_offer(BoardSource.JUSTJOIN, "1"),
        _make_offer(BoardSource.NOFLUFF, "2"),
    ]
    storage.upsert_board_offers(offers)

    listed = storage.list_board_offers()
    keys = {o.offer_key for o in listed}
    assert keys == {"justjoin:1", "nofluff:2"}


def test_upsert_updates_existing_offer_fields(storage: Storage) -> None:
    original = _make_offer(BoardSource.JUSTJOIN, "1", title="Old title")
    storage.upsert_board_offers([original])

    updated = _make_offer(BoardSource.JUSTJOIN, "1", title="New title")
    storage.upsert_board_offers([updated])

    loaded = storage.load_board_offer("justjoin:1")
    assert loaded is not None
    assert loaded.title == "New title"


def test_mark_missing_inactive_flags_stale_offers_only_for_source(
    storage: Storage,
) -> None:
    jjit_a = _make_offer(BoardSource.JUSTJOIN, "a")
    jjit_b = _make_offer(BoardSource.JUSTJOIN, "b")
    nfj = _make_offer(BoardSource.NOFLUFF, "x")
    storage.upsert_board_offers([jjit_a, jjit_b, nfj])

    storage.mark_missing_inactive(BoardSource.JUSTJOIN, ["justjoin:a"])

    assert storage.load_board_offer("justjoin:a").is_active is True
    assert storage.load_board_offer("justjoin:b").is_active is False
    assert storage.load_board_offer("nofluff:x").is_active is True


def test_mark_missing_inactive_with_empty_list_disables_all_from_source(
    storage: Storage,
) -> None:
    storage.upsert_board_offers(
        [
            _make_offer(BoardSource.BULLDOGJOB, "1"),
            _make_offer(BoardSource.BULLDOGJOB, "2"),
        ]
    )
    storage.mark_missing_inactive(BoardSource.BULLDOGJOB, [])

    assert all(o.is_active is False for o in storage.list_board_offers())


def test_list_board_offers_can_exclude_inactive(storage: Storage) -> None:
    storage.upsert_board_offers(
        [
            _make_offer(BoardSource.PRACUJ, "1"),
            _make_offer(BoardSource.PRACUJ, "2"),
        ]
    )
    storage.mark_missing_inactive(BoardSource.PRACUJ, ["pracuj:1"])

    active_only = storage.list_board_offers(include_inactive=False)
    assert [o.offer_key for o in active_only] == ["pracuj:1"]


def test_save_and_get_match_roundtrip(storage: Storage) -> None:
    storage.save_match(
        profile_name="Jan",
        offer_key="justjoin:1",
        match_score=75,
        matched=["Python", "FastAPI"],
        missing=["Terraform"],
    )
    match = storage.get_match(profile_name="Jan", offer_key="justjoin:1")
    assert match is not None
    assert match["match_score"] == 75
    assert match["matched"] == ["Python", "FastAPI"]
    assert match["missing"] == ["Terraform"]


def test_save_match_upserts_on_conflict(storage: Storage) -> None:
    storage.save_match(
        profile_name="Jan",
        offer_key="justjoin:1",
        match_score=40,
        matched=[],
        missing=[],
    )
    storage.save_match(
        profile_name="Jan",
        offer_key="justjoin:1",
        match_score=88,
        matched=["Python"],
        missing=[],
    )
    match = storage.get_match(profile_name="Jan", offer_key="justjoin:1")
    assert match is not None
    assert match["match_score"] == 88


def test_find_cv_for_offer_returns_latest(
    storage: Storage, tmp_path: Path, sample_tailored_cv
) -> None:
    file_path = tmp_path / "cv.docx"
    file_path.write_bytes(b"x")

    storage.record_generated_cv(
        profile_name="Jan",
        job_slug="jjit_1",
        file_path=file_path,
        cv=sample_tailored_cv,
        offer_key="justjoin:1",
    )
    found = storage.find_cv_for_offer(profile_name="Jan", offer_key="justjoin:1")
    assert found is not None
    assert found["offer_key"] == "justjoin:1"
    assert found["job_slug"] == "jjit_1"


def test_find_cv_for_offer_returns_none_when_no_match(
    storage: Storage, sample_tailored_cv
) -> None:
    assert (
        storage.find_cv_for_offer(profile_name="Nobody", offer_key="x:y") is None
    )
    _ = sample_tailored_cv
