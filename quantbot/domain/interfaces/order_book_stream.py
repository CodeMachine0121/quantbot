# quantbot/domain/interfaces/order_book_stream.py
from collections.abc import AsyncIterator
from typing import Protocol

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.order_book_update import OrderBookUpdate


class OrderBookStream(Protocol):
    """即時的掛單簿增量更新。"""

    def updates(self, listing: Listing) -> AsyncIterator[OrderBookUpdate]: ...
