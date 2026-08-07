# quantbot/infrastructure/binance/binance_stream_url_builder.py
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market


class BinanceStreamUrlBuilder:
    """即時連線的網址規則：WebSocket 訂閱與 REST 快照。

    跟 Day 03 的 BinanceArchiveUrlBuilder 分開，因為它們是三個不同的網域、
    三種不同的失效方式（批次檔沒上傳、WebSocket 斷線、REST 被限流）。
    共用一個 builder 只會讓「換 testnet」這種需求同時動到不該動的路徑。

    stream 的路徑一律要小寫的原生 symbol：btcusdt@aggTrade。大寫不會被拒絕，
    但也不會有任何資料推過來，這是新手接 WebSocket 最常見的第一個坑。
    """

    WEBSOCKET_BASE_URLS: ClassVar[Mapping[Market, str]] = MappingProxyType(
        {
            Market.SPOT: "wss://stream.binance.com:9443",
            Market.USD_MARGINED_PERPETUAL: "wss://fstream.binance.com",
        }
    )
    REST_BASE_URLS: ClassVar[Mapping[Market, str]] = MappingProxyType(
        {
            Market.SPOT: "https://api.binance.com",
            Market.USD_MARGINED_PERPETUAL: "https://fapi.binance.com",
        }
    )
    DEPTH_SNAPSHOT_PATHS: ClassVar[Mapping[Market, str]] = MappingProxyType(
        {
            Market.SPOT: "/api/v3/depth",
            Market.USD_MARGINED_PERPETUAL: "/fapi/v1/depth",
        }
    )

    def combined_stream(self, listing: Listing, *, streams: tuple[str, ...]) -> str:
        """一條連線訂閱多個 stream。

        兩個 stream 各開一條連線也能跑，但合併訂閱有一個實際好處：兩邊的訊息
        在同一條 TCP 連線上依序抵達，斷線時一起斷，不會出現「成交還在來、
        掛單簿早就停了」這種只有事後對帳才看得出來的狀態。
        """
        symbol = listing.native_symbol.lower()
        joined = "/".join(f"{symbol}@{stream}" for stream in streams)
        return f"{self.WEBSOCKET_BASE_URLS[listing.market]}/stream?streams={joined}"

    def depth_snapshot(self, listing: Listing, *, depth: int) -> str:
        base = self.REST_BASE_URLS[listing.market]
        path = self.DEPTH_SNAPSHOT_PATHS[listing.market]
        return f"{base}{path}?symbol={listing.native_symbol}&limit={depth}"
