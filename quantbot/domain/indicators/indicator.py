# quantbot/domain/indicators/indicator.py
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries


class Indicator(ABC):
    """所有指標的共同基底。

    這裡用 ABC 而不是 Protocol，因為它有共用實作要給子類別：契約的前四條由
    compute() 擔保，子類別只實作 name 與 _compute 兩件事。對外相依才用 Protocol。
    """

    def __init__(self, period: int, *, column: str = "close") -> None:
        if period < 1:
            raise ValueError(f"period 必須 >= 1，收到 {period}")
        self.period = period
        self.column = column

    @property
    @abstractmethod
    def name(self) -> str:
        """輸出 Series 的名字，慣例是 {indicator}_{period}。"""

    @abstractmethod
    def _compute(self, values: pd.Series) -> pd.Series:
        """真正的計算。拿到的是已經轉好型別的單欄序列。"""

    @property
    def warmup_bar_count(self) -> int:
        """暖機期幾根。SMA 覆寫成 period - 1，EMA 與 RSI 用這個預設值。"""
        return self.period

    def compute(self, series: CandleSeries) -> pd.Series:
        """算出指標，回傳與輸入等長、index 完全相同的 Series。

        這裡不檢查「index 有沒有排序」：CandleSeries 建構時就排好了，
        不變式一旦放進型別，下游的防禦性檢查就是死碼。
        """
        candles = series.frame
        if self.column not in candles.columns:
            raise KeyError(f"沒有 {self.column!r} 欄：{list(candles.columns)}")

        # astype 會複製，所以 _compute 怎麼寫都動不到呼叫端的資料
        values = candles[self.column].astype("float64")
        return self._compute(values).reindex(candles.index).rename(self.name)
