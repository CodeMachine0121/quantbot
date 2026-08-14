# quantbot/domain/services/strategy_correlation_service.py
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


class StrategyCorrelationService:
    """幾個策略的報酬序列兩兩相關。

    它回答的是一個排行榜答不出來的問題：**同時上線的兩個策略，是不是同一個賭注。**
    兩個報酬相關性 0.9 的策略各下一半資金，風險跟只下一個策略但全額投入幾乎一樣，
    而報表上會顯示「已分散到兩個策略」。

    只算兩邊都有部位的那些根，是這裡唯一需要判斷的事。空手的根報酬是 0，而一堆 0
    會把相關係數往 0 拉——兩個曝險都很低的策略（Day 18 的均值回歸只有 1.35%）
    幾乎永遠算出接近 0 的相關性，即使它們每次進場都在同一個時間點。
    """

    def matrix(self, returns_by_strategy: Mapping[str, pd.Series]) -> pd.DataFrame:
        """相關係數矩陣。只用兩邊都有部位的那些根。"""
        if len(returns_by_strategy) < 2:
            raise ValueError("至少要兩個策略才算得出相關性")

        names = list(returns_by_strategy)
        matrix = pd.DataFrame(float("nan"), index=names, columns=names, dtype="float64")
        for first in names:
            matrix.loc[first, first] = 1.0
            for second in names:
                if first >= second:
                    continue
                value = self.pairwise(
                    returns_by_strategy[first], returns_by_strategy[second]
                )
                matrix.loc[first, second] = value
                matrix.loc[second, first] = value
        return matrix

    @staticmethod
    def pairwise(first: pd.Series, second: pd.Series) -> float:
        """兩個策略的相關係數。兩邊都空手的根不算。

        回 NaN 而不是 0 的情況：重疊的根數少於 3，或其中一邊在重疊區間內完全沒有
        變動。那時候相關性沒有定義，而回 0 會被讀成「完全不相關」——那是一個
        很強的結論，不該由「沒有資料」產生。
        """
        aligned = pd.concat([first, second], axis=1, join="inner").dropna()
        if aligned.empty:
            return float("nan")
        active = aligned.loc[(aligned.iloc[:, 0] != 0.0) | (aligned.iloc[:, 1] != 0.0)]
        if len(active) < 3:
            return float("nan")
        return float(active.iloc[:, 0].corr(active.iloc[:, 1]))
