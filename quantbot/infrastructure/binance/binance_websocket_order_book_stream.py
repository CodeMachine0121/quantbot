# quantbot/infrastructure/binance/binance_websocket_order_book_stream.py
from __future__ import annotations

from collections.abc import AsyncIterator

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.infrastructure.binance.binance_stream_payload_parser import (
    BinanceStreamPayloadParser,
)
from quantbot.infrastructure.binance.binance_websocket_message_source import (
    BinanceWebsocketMessageSource,
)


class BinanceWebsocketOrderBookStream:
    """即時掛單簿增量更新。實作 domain 的 OrderBookStream。

    它跟成交那支是同一個形狀，只差過濾哪個 stream 與交給 parser 的哪個方法。
    刻意寫成兩個類別而不是一個帶參數的：它們回傳的是兩種不同的東西，
    硬併成一個就得回傳聯集型別，讓每個呼叫端自己 isinstance 分流。
    """

    def __init__(
        self,
        messages: BinanceWebsocketMessageSource,
        parser: BinanceStreamPayloadParser,
        *,
        streams: tuple[str, ...],
    ) -> None:
        self._messages = messages
        self._parser = parser
        self._streams = streams

    async def updates(self, listing: Listing) -> AsyncIterator[OrderBookUpdate]:
        wanted = f"{listing.native_symbol.lower()}@{self._parser.DEPTH_STREAM}"
        async for frame in self._messages.messages(listing, streams=self._streams):
            if self._parser.stream_name(frame) == wanted:
                yield self._parser.depth_update(frame)
