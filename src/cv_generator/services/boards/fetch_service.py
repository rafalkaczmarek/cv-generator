"""Orchestrates parallel fetching across all board clients and persists results."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from cv_generator.models import BoardOffer, BoardSource
from cv_generator.services.boards.base import BoardClient, BoardQuery
from cv_generator.services.boards.bulldogjob import BulldogjobClient
from cv_generator.services.boards.filters import filter_board_offers
from cv_generator.services.boards.justjoin import JustJoinClient
from cv_generator.services.boards.nofluff import NoFluffClient
from cv_generator.services.boards.pracuj import PracujClient
from cv_generator.services.boards.theprotocol import TheProtocolClient
from cv_generator.services.storage import Storage

logger = logging.getLogger(__name__)


DEFAULT_CLIENT_FACTORIES: dict[BoardSource, type[BoardClient]] = {
    BoardSource.JUSTJOIN: JustJoinClient,
    BoardSource.NOFLUFF: NoFluffClient,
    BoardSource.BULLDOGJOB: BulldogjobClient,
    BoardSource.PRACUJ: PracujClient,
    BoardSource.THEPROTOCOL: TheProtocolClient,
}


@dataclass
class BoardFetchResult:
    """Summary of a single refresh run — per source."""

    fetched: dict[BoardSource, int] = field(default_factory=dict)
    inactivated: dict[BoardSource, int] = field(default_factory=dict)
    errors: dict[BoardSource, str] = field(default_factory=dict)

    @property
    def total_fetched(self) -> int:
        return sum(self.fetched.values())

    @property
    def any_errors(self) -> bool:
        return bool(self.errors)


class BoardFetchService:
    """Fetches offers from all requested boards concurrently."""

    def __init__(
        self,
        *,
        storage: Storage | None = None,
        clients: dict[BoardSource, BoardClient] | None = None,
    ) -> None:
        self._storage = storage or Storage()
        if clients is None:
            clients = {source: cls() for source, cls in DEFAULT_CLIENT_FACTORIES.items()}
        self._clients = clients

    @property
    def storage(self) -> Storage:
        return self._storage

    def refresh(
        self,
        *,
        sources: list[BoardSource] | None = None,
        query: BoardQuery | None = None,
    ) -> BoardFetchResult:
        query = query or BoardQuery()
        active_sources = sources or list(self._clients.keys())
        result = BoardFetchResult()

        client_map = {s: self._clients[s] for s in active_sources if s in self._clients}
        if not client_map:
            return result

        logger.info("Refreshing boards sources=%s", [s.value for s in client_map])
        with ThreadPoolExecutor(max_workers=len(client_map)) as executor:
            future_to_source = {
                executor.submit(_safe_fetch, client, query): source
                for source, client in client_map.items()
            }
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    offers, error = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    result.errors[source] = str(exc)
                    logger.exception("Unexpected failure fetching %s", source.value)
                    continue

                if error:
                    result.errors[source] = error
                if offers:
                    offers = filter_board_offers(
                        offers,
                        keywords=query.keywords,
                        require_keywords=False,
                    )
                if offers:
                    self._storage.upsert_board_offers(offers)
                    result.fetched[source] = len(offers)
                    seen_keys = [o.offer_key for o in offers]
                    result.inactivated[source] = self._storage.mark_missing_inactive(
                        source, seen_keys
                    )
                else:
                    result.fetched[source] = 0

        logger.info(
            "Board refresh finished fetched=%s inactivated=%s errors=%s",
            {s.value: n for s, n in result.fetched.items()},
            {s.value: n for s, n in result.inactivated.items()},
            {s.value: msg for s, msg in result.errors.items()},
        )
        return result


def _safe_fetch(
    client: BoardClient, query: BoardQuery
) -> tuple[list[BoardOffer], str | None]:
    """Never raise across the thread pool boundary — return an error message."""
    try:
        offers = client.fetch_offers(query=query)
        return offers, None
    except Exception as exc:
        logger.warning("Board fetch failed for %s: %s", client.source.value, exc)
        return [], str(exc)


__all__ = ["BoardFetchResult", "BoardFetchService", "DEFAULT_CLIENT_FACTORIES"]
