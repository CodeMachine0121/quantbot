# quantbot/domain/strategies/event_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.feature_parameters import FeatureParameters


class Event(Condition):
    """一個事件型特徵在這一根有沒有發生。

    Day 13 的突破是 0 與 1 兩種值的特徵，拿它跟 0.5 比大小可以，但那個寫法把
    「這是事件」的資訊藏進了一個閾值。所以事件有自己的條件，讀起來也是它的意思：
    `breakout_high_20` 發生了。

    這個條件的統計後果在 Day 13 講過，值得在寫策略時再想一次：事件型條件的樣本數
    是**事件數**，不是 K 線數。13,848 根 1 小時 K 線只有 1,356 次向上突破，而其中
    只有 125 次守住——一個以它為進場觸發的策略，可用的樣本比看起來少兩個數量級。
    這件事 Day 21 會再算一次帳。
    """

    def __init__(self, feature: str) -> None:
        self._feature = feature

    @property
    def name(self) -> str:
        return f"{self._feature}_fired"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset({self._feature})

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def describe(self) -> str:
        return f"{self._feature} 發生"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        """非零且非缺值才算發生。

        兩個條件都要寫出來：`values != 0` 對 NaN 回 True（NaN 不等於 0），所以
        少了 notna() 的話暖機期會被算成一連串事件。
        """
        values = table[self._feature]
        return values.notna() & (values != 0)


class EventBuilder:
    """設定檔的 event。"""

    @property
    def kind(self) -> str:
        return "event"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Event:
        if children:
            raise ValueError("event 是葉條件，不接子節點")
        return Event(feature=parameters.text("feature"))
