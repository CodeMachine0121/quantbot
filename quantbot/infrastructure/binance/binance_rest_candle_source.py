# quantbot/infrastructure/binance/binance_rest_candle_source.py
from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from types import MappingProxyType
from typing import Any, ClassVar

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.infrastructure.binance.binance_rate_limit_guard import (
    BinanceRateLimitGuard,
)


class BinanceRestCandleSource:
    """Binance REST 這條來源。實作 domain 的 CandleSource。

    翻頁邏輯與「只回已收盤的 K 線」都在這裡；區間由呼叫端決定，
    限流交給 BinanceRateLimitGuard。
    """

    REST_COLUMNS: ClassVar[tuple[str, ...]] = (
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    CCXT_MARKET_TYPES: ClassVar[Mapping[Market, str]] = MappingProxyType(
        {
            Market.SPOT: "spot",
            Market.USD_MARGINED_PERPETUAL: "future",
        }
    )

    def __init__(
        self,
        exchange: Any,
        guard: BinanceRateLimitGuard,
        *,
        page_size: int = 1000,
    ) -> None:
        self._exchange = exchange
        self._guard = guard
        self._page_size = page_size

    async def load(self, instrument: Instrument, period: TimeRange) -> CandleSeries:
        step_milliseconds = int(instrument.timeframe.step.total_seconds() * 1000)
        cursor = int(period.start.timestamp() * 1000)
        until = int(period.end.timestamp() * 1000)
        rows: list[list[float]] = []

        while cursor < until:
            # 用 partial 把這一輪的 cursor 綁進去。寫成 lambda 也能跑，
            # 但閉包抓的是變數而不是值，重試時很容易抓到已經被推進過的游標。
            page = await self._guard.call(
                partial(
                    self._exchange.fetch_ohlcv,
                    instrument.symbol,
                    instrument.timeframe.value,
                    since=cursor,
                    limit=self._page_size,
                )
            )
            if not page:
                break

            rows.extend(page)
            # since 是含頭的，所以下一頁要 +1 個間隔
            next_cursor = page[-1][0] + step_milliseconds
            if next_cursor <= cursor:
                break  # 交易所回了同一頁，再翻下去會是無窮迴圈
            cursor = next_cursor

            await self._guard.yield_if_heavy(self._exchange)

        return self._to_series(instrument, rows).restricted_to(period)

    def _to_series(
        self, instrument: Instrument, rows: list[list[float]]
    ) -> CandleSeries:
        candles = pd.DataFrame(rows, columns=list(self.REST_COLUMNS))
        open_times = CandleColumns.to_utc(candles["open_time"])
        open_times.name = CandleColumns.OPEN_TIME
        candles = candles.set_index(open_times)
        return CandleSeries(instrument, candles[~candles.index.duplicated(keep="last")])
