# quantbot/domain/values/candle_columns.py
from __future__ import annotations

from typing import ClassVar, Literal

import pandas as pd


class CandleColumns:
    """K 線的欄位語彙：叫什麼、什麼型別、對齊成什麼形狀。

    整個專案只有這裡知道欄位清單。要注意它**不**知道「官方 CSV 的第幾欄是
    什麼」——那是 Binance 的格式知識，屬於 infrastructure 的 parser。
    """

    OPEN_TIME: ClassVar[str] = "open_time"
    FLOAT_COLUMNS: ClassVar[tuple[str, ...]] = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    )
    INTEGER_COLUMNS: ClassVar[tuple[str, ...]] = ("trade_count",)

    @classmethod
    def all_columns(cls) -> tuple[str, ...]:
        """落地後的欄位與順序。每條資料來源都要對齊到這一份。"""
        return cls.FLOAT_COLUMNS + cls.INTEGER_COLUMNS

    @classmethod
    def conform(cls, candles: pd.DataFrame) -> pd.DataFrame:
        """轉型並補齊欄位，讓每條來源都產出同一種表。

        批次檔有 12 欄，REST 只回 6 欄。不先對齊就 concat，欄位順序會隨著哪條
        路徑先進來而變，而缺的整數欄會被迫轉成 float，所以整數欄用可空的 Int64。
        """
        conformed = pd.DataFrame(index=candles.index)
        for column in cls.FLOAT_COLUMNS:
            conformed[column] = (
                candles[column].astype("float64")
                if column in candles
                else pd.Series(float("nan"), index=candles.index, dtype="float64")
            )
        for column in cls.INTEGER_COLUMNS:
            conformed[column] = (
                candles[column].astype("Int64")
                if column in candles
                else pd.Series(pd.NA, index=candles.index, dtype="Int64")
            )
        return conformed.sort_index()

    @staticmethod
    def to_utc(epochs: pd.Series) -> pd.Series:
        """epoch 整數轉 UTC 時間，單位用數量級判斷，NEVER 寫死。

        毫秒是 13 位數（約 1.7e12），微秒是 16 位數（約 1.7e15），差三個數量級。
        """
        numeric = pd.to_numeric(epochs)
        magnitude = int(numeric.max()) if len(numeric) else 0
        unit: Literal["s", "ms", "us"]
        if magnitude < 10**11:
            unit = "s"
        elif magnitude < 10**14:
            unit = "ms"
        else:
            unit = "us"
        return pd.to_datetime(numeric, unit=unit, utc=True)
