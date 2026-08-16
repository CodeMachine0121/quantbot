# quantbot/domain/strategies/crossover_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.indicators.crossover_signals import CrossoverSignals
from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.cross_direction import CrossDirection
from quantbot.domain.values.feature_parameters import FeatureParameters


class Crossover(Condition):
    """兩條線交叉的那一根。

    它直接重用 Day 04 的 CrossoverSignals，而不是在這裡重寫一次狀態翻轉的判斷。
    那個類別當初就把三件事處理掉了：只有翻轉的那一根為 True、暖機期一律 False、
    以及「前一根也必須是有效值」——少了最後那一條，暖機期結束的第一根會被算成
    一次交叉，因為它的前一根是 NaN 而 NaN 比什麼都不是。

    這裡只取 golden 與 death，NEVER 取那個類別的 entry 與 exit。後兩者已經位移過
    一根，而位移是引擎的職責（見 StrategyEngine）。條件回報的一律是「第 t 根
    的事實」，位移只做一次，做在唯一的地方。
    """

    def __init__(self, fast: str, direction: CrossDirection, slow: str) -> None:
        self._fast = fast
        self._direction = direction
        self._slow = slow

    @property
    def name(self) -> str:
        return f"{self._fast}_cross_{self._direction}_{self._slow}"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset({self._fast, self._slow})

    @property
    def warmup_bar_count(self) -> int:
        """要看前一根的狀態才知道有沒有翻轉，所以比特徵的暖機期再多一根。"""
        return 1

    def describe(self) -> str:
        arrow = "↑" if self._direction is CrossDirection.UP else "↓"
        return f"{self._fast} {arrow} cross {self._slow}"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        signals = CrossoverSignals(table[self._fast], table[self._slow])
        return signals.golden if self._direction is CrossDirection.UP else signals.death


class CrossoverBuilder:
    """設定檔的 crossover。"""

    @property
    def kind(self) -> str:
        return "crossover"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Crossover:
        if children:
            raise ValueError("crossover 是葉條件，不接子節點")
        return Crossover(
            fast=parameters.text("fast"),
            direction=CrossDirection.parse(parameters.text("direction")),
            slow=parameters.text("slow"),
        )
