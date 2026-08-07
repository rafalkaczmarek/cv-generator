"""Tests for BoardOffer / BoardSource models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from cv_generator.models import BoardOffer, BoardSource


def test_board_offer_key_combines_source_and_id() -> None:
    offer = BoardOffer(
        source=BoardSource.JUSTJOIN,
        external_id="abc123",
        url="https://example.com/offer/abc123",
        title="Python Dev",
    )
    assert offer.offer_key == "justjoin:abc123"


def test_board_offer_make_key_accepts_enum_or_string() -> None:
    assert BoardOffer.make_key(BoardSource.NOFLUFF, "x") == "nofluff:x"
    assert BoardOffer.make_key("bulldogjob", "y") == "bulldogjob:y"


def test_board_offer_defaults_active_and_no_last_seen() -> None:
    offer = BoardOffer(
        source=BoardSource.THEPROTOCOL,
        external_id="42",
        url="https://theprotocol.it/x",
        title="Backend",
    )
    assert offer.is_active is True
    assert offer.last_seen_at is None
    assert offer.skills == []


def test_board_offer_requires_url_and_source() -> None:
    with pytest.raises(ValidationError):
        BoardOffer(source=BoardSource.PRACUJ, external_id="1", title="x")  # type: ignore[call-arg]


def test_board_offer_serialises_with_datetime() -> None:
    offer = BoardOffer(
        source=BoardSource.JUSTJOIN,
        external_id="abc",
        url="https://example.com",
        title="Dev",
        published_at=datetime(2026, 1, 2, 12, 0),
    )
    payload = offer.model_dump_json()
    restored = BoardOffer.model_validate_json(payload)
    assert restored.published_at == datetime(2026, 1, 2, 12, 0)
    assert restored.source is BoardSource.JUSTJOIN
