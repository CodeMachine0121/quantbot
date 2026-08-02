# quantbot/domain/indicators/rsi.py
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from quantbot.domain.indicators.indicator import Indicator


class WilderSmoother:
    """Wilder 平滑（也叫 RMA、SMMA）：alpha = 1/period。

    獨立成一個類別是因為它是 RSI 最容易寫錯的一行：alpha 是 1/n，
    NEVER 寫成 ewm(span=n)——那是 EMA 的 2/(n+1)，差了將近一倍，
    而算出來的東西照樣落在 0 到 100 之間，只有對照組看得出差別。

    它跟 RSI 住同一個檔案，因為目前只為 RSI 存在；哪天 ATR 也要用，再搬出去。
    """

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f"period 必須 >= 1，收到 {period}")
        self.period = period

    @property
    def alpha(self) -> float:
        return 1.0 / self.period

    def smooth(self, values: pd.Series) -> pd.Series:
        """平滑一條序列，起始值用前 period 筆的算術平均。

        values 的第 0 筆是 diff() 產生的 NaN，所以種子取 values[1:period+1]，
        放在第 period 個位置，遞迴從第 period + 1 筆開始。
        """
        seeded = values.copy()
        seeded.iloc[: self.period] = np.nan
        seeded.iloc[self.period] = values.iloc[1 : self.period + 1].mean()
        return seeded.ewm(alpha=self.alpha, adjust=False).mean()


class RSI(Indicator):
    """相對強弱指標，值域 0-100。

    全部上漲回傳 100、全部下跌回傳 0、完全持平回傳 NEUTRAL_VALUE（50）。
    最後那個 50 是補的、不是算出來的，所以它是一個具名的類別常數。
    """

    NEUTRAL_VALUE: ClassVar[float] = 50.0

    def __init__(self, period: int = 14, *, column: str = "close") -> None:
        super().__init__(period, column=column)
        self._smoother = WilderSmoother(period)

    @property
    def name(self) -> str:
        return f"rsi_{self.period}"

    def _compute(self, values: pd.Series) -> pd.Series:
        # 資料不足以算出任何有效值時回等長的全 NaN，而不是丟例外：
        # 呼叫端處理的是 NaN，不是 try/except。
        if len(values) <= self.period:
            return pd.Series(np.nan, index=values.index, dtype="float64")

        change = values.diff()
        average_gain = self._smoother.smooth(change.clip(lower=0.0))
        average_loss = self._smoother.smooth((-change).clip(lower=0.0))

        total = average_gain + average_loss
        strength = 100.0 * average_gain / total
        # total == 0 表示這段完全沒動，漲跌力道相當，補中性值。
        # 用 mask 而不是 where(total > 0, 50)：NaN > 0 是 False，
        # 那樣寫會把暖機期的 NaN 一起填成 50。
        return strength.mask(total == 0.0, self.NEUTRAL_VALUE)
