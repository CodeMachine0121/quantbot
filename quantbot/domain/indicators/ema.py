# quantbot/domain/indicators/ema.py
from __future__ import annotations

from typing import ClassVar, Literal

import numpy as np
import pandas as pd

from quantbot.domain.indicators.indicator import Indicator

WarmupMode = Literal["sma", "first"]


class EMA(Indicator):
    """指數移動平均。

    採 adjust=False 的遞迴定義（ema[i] = a * x[i] + (1-a) * ema[i-1]，
    a = 2 / (period + 1)），與上線後逐根更新的算法完全一致。

    種子取法是建構參數：它會影響前面數百根的值，NEVER 讓呼叫端每次隨手決定。
    """

    WARMUP_MODES: ClassVar[tuple[str, ...]] = ("sma", "first")

    def __init__(
        self, period: int, *, column: str = "close", warmup: WarmupMode = "sma"
    ) -> None:
        super().__init__(period, column=column)
        if warmup not in self.WARMUP_MODES:
            raise ValueError(f"未知的種子取法：{warmup!r}")
        self.warmup = warmup

    @property
    def name(self) -> str:
        return f"ema_{self.period}"

    @property
    def alpha(self) -> float:
        """平滑係數 2/(n+1)。Wilder 平滑用的是 1/n，兩者差將近一倍。"""
        return 2.0 / (self.period + 1)

    def required_warmup_bar_count(self, *, safety_factor: int = 5) -> int:
        """建議預留幾根暖機資料才算得準。

        遞迴指標的值取決於從哪裡開始算，所以「要預留多少」必須是問得出來的數字，
        不是口頭約定。
        """
        return safety_factor * self.period

    def _compute(self, values: pd.Series) -> pd.Series:
        if self.warmup == "first":
            return values.ewm(span=self.period, adjust=False).mean()

        if len(values) < self.period:
            # 資料不足以生出種子。NEVER 拿半個視窗硬算出一個看起來合理的值，
            # 那種值不會噴錯，只會安靜地汙染後面所有計算。
            return pd.Series(np.nan, index=values.index, dtype="float64")

        seeded = values.copy()
        seeded.iloc[: self.period - 1] = np.nan
        seeded.iloc[self.period - 1] = values.iloc[: self.period].mean()
        return seeded.ewm(span=self.period, adjust=False).mean()
