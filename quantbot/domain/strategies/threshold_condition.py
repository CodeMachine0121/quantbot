# quantbot/domain/strategies/threshold_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.feature_parameters import FeatureParameters


class Threshold(Condition):
    """一個特徵跟一個常數比大小。「RSI 低於 70」就是這個。

    它是最常用也最容易被誤用的條件。誤用的方式是把它當成預測：RSI 高於 70 不代表
    要跌（Day 06 講過，強趨勢裡它可以貼著 80 走很久），所以它適合當**過濾**——
    否決一個已經成立的進場——而不是自己當進場理由。

    常數的單位是特徵自己的單位，所以閾值不能跨特徵抄。RSI 的 70 是 0–100 的刻度，
    活躍度的 2.0 是標準差，ATR 的 300 是 USDT。這也是 Day 12 把活躍度做成 z-score
    的理由：標準化過的特徵，閾值才有辦法在不同交易對之間沿用。
    """

    def __init__(self, feature: str, comparison: Comparison, value: float) -> None:
        self._feature = feature
        self._comparison = comparison
        self._value = value

    @property
    def name(self) -> str:
        return f"{self._feature}_{self._comparison}_{self._value:g}"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset({self._feature})

    @property
    def warmup_bar_count(self) -> int:
        """不需要前一根，所以是 0。特徵自己的暖機期由 Day 15 的管線負責。"""
        return 0

    def describe(self) -> str:
        return f"{self._feature} {self._comparison.symbol} {self._value:g}"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return self._comparison.applies(table[self._feature], self._value)


class ThresholdBuilder:
    """設定檔的 threshold。"""

    @property
    def kind(self) -> str:
        return "threshold"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Threshold:
        if children:
            raise ValueError("threshold 是葉條件，不接子節點")
        return Threshold(
            feature=parameters.text("feature"),
            comparison=Comparison.parse(parameters.text("comparison")),
            value=parameters.number("value"),
        )
