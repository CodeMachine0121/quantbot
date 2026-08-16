# quantbot/domain/strategies/sustained_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.feature_parameters import FeatureParameters


class Sustained(Condition):
    """另一個條件連續成立 N 根才算成立。

    它是第一個**修飾**條件的條件——`AllOf` 與 `Not` 組合的是同一根的判斷，這個看的
    是時間軸上的一段。所以組合運算子那套代數不只有三個運算子：任何「吃一個條件、
    回一個條件」的東西都接得上，因為進出的形狀相同。

    它為什麼值得進積木庫，而不是寫死在某個策略裡：兩個策略都需要它，而且需要的
    理由一樣。均值回歸不希望價格只是短暫戳破偏離門檻就進場（那多半是一根長影線），
    動能爆發不希望一根暴量就當成趨勢。兩者要的都是「這個狀態站得住」。
    Day 16 那條判準是「會被第二個策略用到才抽象化」，這裡剛好踩在線上。

    暖機期是子條件的暖機期再加 bars - 1：要湊滿 N 根才答得出第一個 True。
    """

    def __init__(self, condition: Condition, bars: int) -> None:
        if bars < 2:
            raise ValueError(
                f"sustained 的 bars 必須 >= 2，收到 {bars}（1 根等於不修飾）"
            )
        self._condition = condition
        self._bars = bars

    @property
    def condition(self) -> Condition:
        return self._condition

    @property
    def name(self) -> str:
        return f"sustained_{self._bars}({self._condition.name})"

    @property
    def required_features(self) -> frozenset[str]:
        return self._condition.required_features

    @property
    def warmup_bar_count(self) -> int:
        return self._condition.warmup_bar_count + self._bars - 1

    def describe(self) -> str:
        return f"{self._condition.describe()} 連續 {self._bars} 根"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        """滾動求和等於視窗長度，就是「這 N 根全部成立」。

        用 rolling().sum() 而不是 N 個 shift() 相 AND：後者的寫法要隨 bars 改變
        程式碼結構，而且 N 大的時候會產生 N 份中間結果。min_periods 用預設值
        （等於視窗長度），所以前 N-1 根是 NaN，而 NaN != bars 的結果是 False——
        正好是要的語意，不必另外處理。
        """
        satisfied = self._condition.evaluate(table).astype("float64")
        return satisfied.rolling(self._bars).sum() == float(self._bars)


class SustainedBuilder:
    """設定檔的 sustained。它是唯一一個既要子節點也要參數的條件。"""

    @property
    def kind(self) -> str:
        return "sustained"

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Sustained:
        if len(children) != 1:
            raise ValueError(f"sustained 只能有一個子節點，實得 {len(children)} 個")
        return Sustained(children[0], parameters.integer("bars"))
