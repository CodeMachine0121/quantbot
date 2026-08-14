# quantbot/domain/strategies/feature_comparison_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.feature_parameters import FeatureParameters


class FeatureComparison(Condition):
    """兩個特徵互相比大小。「收盤價在 VWAP 之上」就是這個。

    它跟 Threshold 只差在右邊是一欄還是一個數字，但那個差別在使用上很關鍵：
    跟常數比需要知道這個市場的價位（BTC 的 50000 對 SOL 毫無意義），跟另一欄比
    不需要。所以能寫成兩欄相比的條件，換交易對時不必重調參數。

    左右兩邊的名字都算在 required_features 裡，這樣使用者只要寫錯一邊，
    載入時就會被指名。
    """

    def __init__(self, left: str, comparison: Comparison, right: str) -> None:
        self._left = left
        self._comparison = comparison
        self._right = right

    @property
    def name(self) -> str:
        return f"{self._left}_{self._comparison}_{self._right}"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset({self._left, self._right})

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def describe(self) -> str:
        return f"{self._left} {self._comparison.symbol} {self._right}"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return self._comparison.applies(table[self._left], table[self._right])


class FeatureComparisonBuilder:
    """設定檔的 compare。"""

    @property
    def kind(self) -> str:
        return "compare"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> FeatureComparison:
        if children:
            raise ValueError("compare 是葉條件，不接子節點")
        return FeatureComparison(
            left=parameters.text("left"),
            comparison=Comparison.parse(parameters.text("comparison")),
            right=parameters.text("right"),
        )
