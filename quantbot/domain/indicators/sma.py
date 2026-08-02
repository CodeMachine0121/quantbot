# quantbot/domain/indicators/sma.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.indicators.indicator import Indicator
from quantbot.domain.indicators.irregular_index_error import IrregularIndexError
from quantbot.domain.values.timeframe import Timeframe


class SMA(Indicator):
    """簡單移動平均。

    一個實例代表一條特定的均線：視窗長度與索引檢查在建構時就固定。
    視窗長度的單位是「幾根 K 線」，不是時間——這個區別是第二個常見錯誤的來源。
    """

    def __init__(
        self,
        period: int,
        *,
        column: str = "close",
        expected_timeframe: Timeframe | None = None,
    ) -> None:
        super().__init__(period, column=column)
        # 給定時會檢查索引是不是完整的等間隔網格，避免視窗悄悄涵蓋更長的時間
        self.expected_timeframe = expected_timeframe

    @property
    def name(self) -> str:
        return f"sma_{self.period}"

    @property
    def warmup_bar_count(self) -> int:
        return self.period - 1  # 只有 SMA 是 n-1

    def _compute(self, values: pd.Series) -> pd.Series:
        self._check_grid(values)
        return values.rolling(window=self.period, min_periods=self.period).mean()

    def _check_grid(self, values: pd.Series) -> None:
        """宣告了 expected_timeframe 就確認網格完整，有洞直接失敗。

        指標算不出正確結果時應該拒絕回傳，而不是回傳一個看起來正常的錯數字。
        """
        if self.expected_timeframe is None or values.empty:
            return
        if not isinstance(values.index, pd.DatetimeIndex):
            raise TypeError("expected_timeframe 需要 DatetimeIndex")

        expected = pd.date_range(
            start=values.index[0],
            end=values.index[-1],
            freq=self.expected_timeframe.pandas_frequency,
            tz=values.index.tz,
        )
        missing = expected.difference(values.index)
        if len(missing) > 0:
            raise IrregularIndexError(
                f"{self.expected_timeframe} 的網格缺了 {len(missing)} 根，"
                f"第一個缺漏在 {missing[0]}"
            )
