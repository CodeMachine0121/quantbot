# quantbot/domain/values/price_source.py
from __future__ import annotations

from enum import StrEnum

import pandas as pd


class PriceSource(StrEnum):
    """一根 K 線要用哪個價格代表它。

    CLOSE 是預設的直覺選擇，但它只採樣一個瞬間——一根長影線的 K 線，收盤價完全
    看不出那一分鐘走過的範圍。TYPICAL 取 (高 + 低 + 收) / 3，把區間也算進去。

    成交量加權的計算慣例用 TYPICAL：VWAP 要回答的是「這段期間市場的平均成本」，
    而成交是散落在整根 K 線的價格區間裡的，不是全部發生在收盤價上。

    這是一個值而不是一個布林參數，因為之後還會有第三種（開高低收的平均）。
    """

    CLOSE = "close"
    TYPICAL = "typical"

    def of(self, candles: pd.DataFrame) -> pd.Series:
        """取出這根 K 線的代表價。轉換只寫在這裡一份。"""
        if self is PriceSource.CLOSE:
            return candles["close"].astype("float64")
        return (
            candles[["high", "low", "close"]].astype("float64").sum(axis=1) / 3.0
        ).rename("typical_price")
