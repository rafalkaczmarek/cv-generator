"""Tests for BoardFetchService orchestration and error isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.boards import BoardFetchService, BoardQuery
from cv_generator.services.boards.base import BoardClientError
from cv_generator.services.storage import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(db_path=tmp_path / "test.sqlite")


class _FakeClient:
    def __init__(self, source: BoardSource, offers: list[BoardOffer]) -> None:
        self.source = source
        self._offers = offers

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        _ = query
        return list(self._offers)


class _FailingClient:
    def __init__(self, source: BoardSource, message: str = "boom") -> None:
        self.source = source
        self._message = message

    def fetch_offers(self, *, query: BoardQuery) -> list[BoardOffer]:
        _ = query
        raise BoardClientError(self._message)


def _offer(
    source: BoardSource,
    external_id: str,
    title: str = "Dev",
    *,
    skills: list[str] | None = None,
    published_at: datetime | None = None,
) -> BoardOffer:
    return BoardOffer(
        source=source,
        external_id=external_id,
        url=f"https://example.com/{source.value}/{external_id}",
        title=title,
        skills=["Python"] if skills is None else skills,
        published_at=published_at or datetime.now(UTC),
    )


def test_refresh_upserts_offers_and_reports_counts(storage: Storage) -> None:
    service = BoardFetchService(
        storage=storage,
        clients={
            BoardSource.JUSTJOIN: _FakeClient(
                BoardSource.JUSTJOIN,
                [_offer(BoardSource.JUSTJOIN, "a"), _offer(BoardSource.JUSTJOIN, "b")],
            ),
            BoardSource.NOFLUFF: _FakeClient(
                BoardSource.NOFLUFF, [_offer(BoardSource.NOFLUFF, "x")]
            ),
        },
    )

    result = service.refresh()

    assert result.fetched[BoardSource.JUSTJOIN] == 2
    assert result.fetched[BoardSource.NOFLUFF] == 1
    assert not result.errors
    keys = {o.offer_key for o in storage.list_board_offers()}
    assert keys == {"justjoin:a", "justjoin:b", "nofluff:x"}


def test_refresh_deactivates_offers_that_disappeared(storage: Storage) -> None:
    initial_clients = {
        BoardSource.JUSTJOIN: _FakeClient(
            BoardSource.JUSTJOIN,
            [_offer(BoardSource.JUSTJOIN, "a"), _offer(BoardSource.JUSTJOIN, "b")],
        )
    }
    BoardFetchService(storage=storage, clients=initial_clients).refresh()

    # Second refresh: only offer "a" is still present.
    second_clients = {
        BoardSource.JUSTJOIN: _FakeClient(
            BoardSource.JUSTJOIN, [_offer(BoardSource.JUSTJOIN, "a")]
        )
    }
    BoardFetchService(storage=storage, clients=second_clients).refresh()

    a = storage.load_board_offer("justjoin:a")
    b = storage.load_board_offer("justjoin:b")
    assert a is not None and a.is_active is True
    assert b is not None and b.is_active is False


def test_refresh_isolates_failing_client_from_others(storage: Storage) -> None:
    service = BoardFetchService(
        storage=storage,
        clients={
            BoardSource.JUSTJOIN: _FakeClient(
                BoardSource.JUSTJOIN, [_offer(BoardSource.JUSTJOIN, "ok")]
            ),
            BoardSource.BULLDOGJOB: _FailingClient(
                BoardSource.BULLDOGJOB, "portal offline"
            ),
        },
    )

    result = service.refresh()

    assert result.fetched.get(BoardSource.JUSTJOIN) == 1
    assert result.errors.get(BoardSource.BULLDOGJOB) == "portal offline"
    assert result.any_errors is True


def test_refresh_respects_source_filter(storage: Storage) -> None:
    service = BoardFetchService(
        storage=storage,
        clients={
            BoardSource.JUSTJOIN: _FakeClient(
                BoardSource.JUSTJOIN, [_offer(BoardSource.JUSTJOIN, "a")]
            ),
            BoardSource.NOFLUFF: _FakeClient(
                BoardSource.NOFLUFF, [_offer(BoardSource.NOFLUFF, "x")]
            ),
        },
    )

    result = service.refresh(sources=[BoardSource.JUSTJOIN])

    assert BoardSource.JUSTJOIN in result.fetched
    assert BoardSource.NOFLUFF not in result.fetched
    keys = {o.offer_key for o in storage.list_board_offers()}
    assert keys == {"justjoin:a"}


def test_refresh_persists_only_recent_keyword_matches(storage: Storage) -> None:
    now = datetime.now(UTC)
    keep = _offer(BoardSource.JUSTJOIN, "keep", title="Python backend", published_at=now)
    old = _offer(
        BoardSource.JUSTJOIN,
        "old",
        title="Python backend",
        published_at=now - timedelta(days=5),
    )
    mismatch = _offer(
        BoardSource.JUSTJOIN,
        "go",
        title="Go engineer",
        skills=["Go"],
        published_at=now,
    )
    service = BoardFetchService(
        storage=storage,
        clients={
            BoardSource.JUSTJOIN: _FakeClient(
                BoardSource.JUSTJOIN, [keep, old, mismatch]
            )
        },
    )

    result = service.refresh(query=BoardQuery(keywords=["Python"]))

    assert result.fetched[BoardSource.JUSTJOIN] == 1
    keys = {o.offer_key for o in storage.list_board_offers()}
    assert keys == {"justjoin:keep"}
