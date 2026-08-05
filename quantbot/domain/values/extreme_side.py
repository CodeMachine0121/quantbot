# quantbot/domain/values/extreme_side.py
from __future__ import annotations

from enum import StrEnum

import pandas as pd


class ExtremeSide(StrEnum):
    """要看前高還是前低。

    兩者不是「同一件事換個方向」——它們用的欄位不同（high 對 low）、比較方向不同
    （突破是大於前高，跌破是小於前低），而且 rolling 的聚合函式也不同。把它們寫成
    一個帶 bool 參數的函式，會讓每個呼叫端都要自己記得三件事要一起翻。
    """

    HIGH = "high"
    LOW = "low"

    @property
    def column(self) -> str:
        return str(self.value)

    def rolling_extreme(self, values: pd.Series, window: int) -> pd.Series:
        """過去 window 根的極值。**呼叫端負責先 shift**，這裡不做。

        不在這裡 shift 是刻意的：要不要含當根，是使用這個值的人才知道的事
        （畫圖時想含、判斷突破時 NEVER 含），寫死在這裡會讓其中一種用法
        必須繞過它。PriorExtreme 那個特徵才是「保證不含當根」的那一層。
        """
        window_view = values.rolling(window)
        return window_view.max() if self is ExtremeSide.HIGH else window_view.min()

    def breaks(self, values: pd.Series, threshold: pd.Series) -> pd.Series:
        """突破的方向。前高要「大於」，前低要「小於」。"""
        return values > threshold if self is ExtremeSide.HIGH else values < threshold
