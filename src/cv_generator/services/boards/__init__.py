"""Polish IT job-board clients and a fetch orchestrator.

Every client implements :class:`BoardClient` and returns ``BoardOffer``
instances. The orchestrator (:class:`BoardFetchService`) runs them in
parallel, upserts results and marks stale offers as inactive.
"""

from cv_generator.services.boards.base import (
    BoardClient,
    BoardClientError,
    BoardQuery,
    build_http_client,
)
from cv_generator.services.boards.bulldogjob import BulldogjobClient
from cv_generator.services.boards.fetch_service import BoardFetchResult, BoardFetchService
from cv_generator.services.boards.filters import (
    filter_board_offers,
    is_recently_published,
    offer_matches_keywords,
)
from cv_generator.services.boards.justjoin import JustJoinClient
from cv_generator.services.boards.nofluff import NoFluffClient
from cv_generator.services.boards.pracuj import PracujClient
from cv_generator.services.boards.theprotocol import TheProtocolClient

__all__ = [
    "BoardClient",
    "BoardClientError",
    "BoardFetchResult",
    "BoardFetchService",
    "BoardQuery",
    "BulldogjobClient",
    "filter_board_offers",
    "is_recently_published",
    "offer_matches_keywords",
    "JustJoinClient",
    "NoFluffClient",
    "PracujClient",
    "TheProtocolClient",
    "build_http_client",
]
