# quantbot/infrastructure/binance/binance_rest_order_book_snapshot_source.py
from __future__ import annotations

from typing import ClassVar

import httpx

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot
from quantbot.infrastructure.binance.binance_snapshot_rate_guard import (
    BinanceSnapshotRateGuard,
)
from quantbot.infrastructure.binance.binance_stream_payload_parser import (
    BinanceStreamPayloadParser,
)
from quantbot.infrastructure.binance.binance_stream_url_builder import (
    BinanceStreamUrlBuilder,
)


class BinanceRestOrderBookSnapshotSource:
    """REST 的深度快照。實作 domain 的 OrderBookSnapshotSource。

    這條路徑會被反覆呼叫——每次序號斷裂都要重拉一次——而且它吃的是跟 Day 03 回補、
    以及之後下單同一個 IP 的 weight 額度。所以它前面掛了一個 guard：
    重拉快照 NEVER 是免費的操作。

    spot 的 /api/v3/depth 按檔數分級收 weight：100 檔以內 5、500 檔 25、
    1000 檔 50、5000 檔 250。深度取多少不只影響資料量，也影響斷線時的成本。
    """

    WEIGHT_BY_DEPTH_CEILING: ClassVar[tuple[tuple[int, int], ...]] = (
        (100, 5),
        (500, 25),
        (1000, 50),
        (5000, 250),
    )

    def __init__(
        self,
        client: httpx.AsyncClient,
        url_builder: BinanceStreamUrlBuilder,
        parser: BinanceStreamPayloadParser,
        guard: BinanceSnapshotRateGuard,
    ) -> None:
        self._client = client
        self._url_builder = url_builder
        self._parser = parser
        self._guard = guard

    @classmethod
    def weight_of(cls, depth: int) -> int:
        """這個深度的快照要付多少 weight。寫成方法是為了能被測試與報告引用。"""
        for ceiling, weight in cls.WEIGHT_BY_DEPTH_CEILING:
            if depth <= ceiling:
                return weight
        raise ValueError(f"depth 超過官方上限 5000：{depth}")

    async def snapshot(self, listing: Listing, *, depth: int) -> OrderBookSnapshot:
        self.weight_of(depth)  # 深度不合法的話在打出去之前就擋掉
        await self._guard.acquire()

        response = await self._client.get(
            self._url_builder.depth_snapshot(listing, depth=depth)
        )
        response.raise_for_status()
        return self._parser.snapshot(response.content)
