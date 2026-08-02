# quantbot/domain/services/candle_sanitation_service.py
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.sanitation_outcome import SanitationOutcome


class CandleSanitationService:
    """入庫前的清洗與異常標記。

    政策只有一條：**結構上不可能為真的丟掉，看起來不對勁但可能是真的保留並標記。**
    市場上真的會出現看起來不合理的資料，要做的是讓它進報告、由人決定，
    而不是讓管線悄悄替我們決定。
    """

    FATAL_FLAGS: ClassVar[tuple[str, ...]] = ("ohlc_invalid", "negative_value")
    # 單根 K 線的合理跳動上限。1 分鐘跳 5% 跟日線跳 5% 是完全不同的事件，
    # 用同一個數字沒有意義，所以門檻跟 timeframe 綁在一起。
    MAXIMUM_ABSOLUTE_RETURNS: ClassVar[Mapping[str, float]] = MappingProxyType(
        {
            "1m": 0.05,
            "5m": 0.08,
            "15m": 0.12,
            "1h": 0.20,
            "4h": 0.30,
            "1d": 0.50,
        }
    )

    def sanitize(self, series: CandleSeries) -> SanitationOutcome:
        candles = series.frame
        flags = self._flag(candles, series.instrument.timeframe.value)
        fatal = flags[list(self.FATAL_FLAGS)].any(axis=1)

        return SanitationOutcome(
            accepted=CandleSeries(series.instrument, candles.loc[~fatal]),
            anomalies=candles.join(flags).loc[flags.any(axis=1)],
        )

    def maximum_absolute_return(self, timeframe_value: str) -> float:
        if timeframe_value not in self.MAXIMUM_ABSOLUTE_RETURNS:
            raise ValueError(f"沒有為 {timeframe_value} 訂跳動門檻")
        return self.MAXIMUM_ABSOLUTE_RETURNS[timeframe_value]

    def _flag(self, candles: pd.DataFrame, timeframe_value: str) -> pd.DataFrame:
        """四個向量化的標記，沒有一行在遍歷 K 線。"""
        body_high = candles[["open", "close"]].max(axis=1)
        body_low = candles[["open", "close"]].min(axis=1)

        flags = pd.DataFrame(index=candles.index)
        flags["ohlc_invalid"] = (
            (candles["high"] < candles["low"])
            | (candles["high"] < body_high)
            | (candles["low"] > body_low)
        )
        flags["negative_value"] = (candles[list(CandleColumns.all_columns())] < 0).any(
            axis=1
        )
        flags["zero_volume"] = candles["volume"].eq(0)
        flags["price_jump"] = candles["close"].pct_change().abs() > (
            self.maximum_absolute_return(timeframe_value)
        )
        return flags
