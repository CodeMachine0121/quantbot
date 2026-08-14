# quantbot/domain/services/performance_metrics_service.py
from __future__ import annotations

import numpy as np
import pandas as pd


class PerformanceMetricsService:
    """從報酬序列算出績效指標。

    今天只有夏普比率一個，因為 Day 21 的搜尋需要一個「單一數字排名」才能示範
    挖礦會發生什麼事。其餘指標（最大回撤、回撤持續時間、索提諾、勝率與賠率）
    Day 22 補上——那一天的主題正是「單一數字排名為什麼會誤導」。

    年化用「一年有幾根」換算，而那個數字由 timeframe 決定，所以它是參數而不是
    常數。1 小時 K 線一年 8,760 根，1 天 K 線 365 根，差 24 倍——寫死任何一個
    都會讓另一個的夏普錯 4.9 倍（根號 24）。
    """

    def sharpe_ratio(
        self, returns: pd.Series, *, periods_per_year: float
    ) -> float | None:
        """年化夏普比率。無風險利率取 0。

        回 None 而不是 0 或 inf 的三種情況：樣本太少（少於兩筆）、標準差為零
        （完全沒有交易的策略，報酬全是 0）、以及標準差算出 NaN。這三種都不是
        「夏普很差」，是「夏普沒有定義」，而把它們當成 0 會讓一個從不交易的策略
        排在賠錢的策略前面。

        無風險利率取 0 是這個系列的簡化，而它在加密貨幣上比在股票上合理——
        這裡的比較對象是「同一段時間的其他策略」，而不是「放定存」。
        """
        cleaned = returns.dropna()
        if len(cleaned) < 2:
            return None
        deviation = float(cleaned.std(ddof=1))
        if deviation == 0.0 or not np.isfinite(deviation):
            return None
        return float(cleaned.mean()) / deviation * float(np.sqrt(periods_per_year))
