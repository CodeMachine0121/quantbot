# tests/reference/reference_rsi.py
"""教科書定義的迴圈版 RSI。只在測試裡當對照組，NEVER 進正式路徑。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ReferenceRSI:
    """照 avg[i] = (avg[i-1] * (n-1) + value[i]) / n 這條原始更新式寫。

    連 100 - 100/(1+RS) 那個式子都照抄，好跟教科書逐行對照——正式版用的是
    等價但不會產生 inf 的另一種寫法，兩邊對得起來才表示代數沒推錯。
    """

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def compute(self, closes: pd.Series) -> pd.Series:
        period = self.period
        gain = closes.diff().clip(lower=0.0).to_numpy()
        loss = (-closes.diff()).clip(lower=0.0).to_numpy()
        count = len(closes)

        average_gain = np.full(count, np.nan)
        average_loss = np.full(count, np.nan)
        average_gain[period] = gain[1 : period + 1].mean()
        average_loss[period] = loss[1 : period + 1].mean()
        for index in range(period + 1, count):
            average_gain[index] = (
                average_gain[index - 1] * (period - 1) + gain[index]
            ) / period
            average_loss[index] = (
                average_loss[index - 1] * (period - 1) + loss[index]
            ) / period

        strength = average_gain / average_loss
        return pd.Series(100 - 100 / (1 + strength), index=closes.index)
