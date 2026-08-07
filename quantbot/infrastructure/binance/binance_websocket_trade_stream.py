# quantbot/infrastructure/binance/binance_websocket_trade_stream.py
from __future__ import annotations

from collections.abc import AsyncIterator

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.trade_event import TradeEvent
from quantbot.infrastructure.binance.binance_stream_payload_parser import (
    BinanceStreamPayloadParser,
)
from quantbot.infrastructure.binance.binance_websocket_message_source import (
    BinanceWebsocketMessageSource,
)


class BinanceWebsocketTradeStream:
    """即時逐筆成交。實作 domain 的 TradeStream。

    這個類別只剩下「訂哪個 stream、收到之後交給誰翻譯、不是這個 stream 的丟掉」。
    連線與重連在 message source，欄名與型別在 parser。合併訂閱的訊息裡兩種都會來，
    所以要過濾——少了這一行，掛單簿的更新會被當成成交去解析並丟出例外。
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

    async def events(self, listing: Listing) -> AsyncIterator[TradeEvent]:
        wanted = f"{listing.native_symbol.lower()}@{self._parser.AGG_TRADE_STREAM}"
        async for frame in self._messages.messages(listing, streams=self._streams):
            if self._parser.stream_name(frame) == wanted:
                yield self._parser.agg_trade(frame)
