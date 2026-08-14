# quantbot/domain/strategies/range_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.feature_parameters import FeatureParameters


class Range(Condition):
    """特徵落在一個區間裡（含兩端）。

    它等於兩個 Threshold 用 AND 接起來，所以嚴格說是多餘的——而它還是值得存在，
    因為「區間」在設定檔裡是一個常見的意圖，寫成一個條件比寫成兩個少一次出錯機會
    （尤其是上下界寫反）。上下界寫反在這裡會直接報錯，寫成兩個 Threshold 則會安靜地
    產出一個永遠不成立的條件。

    這是判斷「該不該進積木庫」的一個實例：它不是為了展示彈性而抽象，是因為它擋掉
    一個具體的錯誤。
    """

    def __init__(self, feature: str, lower: float, upper: float) -> None:
        if lower > upper:
            raise ValueError(f"區間的下界不能大於上界：{lower} > {upper}")
        self._feature = feature
        self._lower = lower
        self._upper = upper

    @property
    def name(self) -> str:
        return f"{self._feature}_in_{self._lower:g}_{self._upper:g}"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset({self._feature})

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def describe(self) -> str:
        return f"{self._lower:g} <= {self._feature} <= {self._upper:g}"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        values = table[self._feature]
        return (values >= self._lower) & (values <= self._upper)


class RangeBuilder:
    """設定檔的 range。"""

    @property
    def kind(self) -> str:
        return "range"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Range:
        if children:
            raise ValueError("range 是葉條件，不接子節點")
        return Range(
            feature=parameters.text("feature"),
            lower=parameters.number("lower"),
            upper=parameters.number("upper"),
        )
