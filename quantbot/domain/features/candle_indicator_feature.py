# quantbot/domain/features/candle_indicator_feature.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.indicators.indicator import Indicator
from quantbot.domain.indicators.registry import INDICATORS
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class CandleIndicatorFeature:
    """把 Day 04 的 Indicator 接進 Feature 協定。實作 domain 的 Feature。

    Day 04–06 的三個指標（SMA、EMA、RSI）繼承的是 `Indicator` ABC，簽章是
    `compute(CandleSeries) -> Series`；Day 10 訂的 `Feature` 協定要的是
    `compute(MarketView) -> Series`。兩者差一個參數型別。

    處理方式有三種，這裡選第三種：

    1. 改 Indicator 的簽章讓它吃 MarketView。那會讓三個已經發佈的指標、它們的
       測試、以及 Day 04–06 的每個範例一起改，而且會讓「只吃 K 線一個欄位」這個
       很有價值的窄契約消失。
    2. 讓 Indicator 同時繼承兩個介面。ABC 加 Protocol 混用，而簽章還是衝突。
    3. **一個轉接器。** 二十行，不動任何既有的東西，而且它把「指標是特徵的一個
       特例」這件事寫成了程式碼。

    這是 Day 06 說「介面要在早期訂死」的兌現方式：早期訂的那個介面不必是萬能的，
    它只要在自己的範圍內正確，而範圍之外用轉接器接上去。
    """

    def __init__(self, indicator: Indicator) -> None:
        self._indicator = indicator

    @property
    def name(self) -> str:
        return self._indicator.name

    @property
    def warmup_bar_count(self) -> int:
        return self._indicator.warmup_bar_count

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        return self._indicator.compute(view.candles)


class CandleIndicatorBuilder:
    """sma、ema、rsi 三個 kind 共用這一個 builder。

    它們的參數形狀完全一樣（period ＋ column），差別只在註冊表裡取到哪個類別，
    所以寫三個一模一樣的 builder 沒有意義。kind 由建構參數決定，而 INDICATORS
    那張表是 Day 06 就存在的——這裡沒有新增任何指標知識。
    """

    def __init__(self, kind: str) -> None:
        if kind not in INDICATORS:
            raise ValueError(f"未知的指標：{kind}（可用：{sorted(INDICATORS)}）")
        self._kind = kind

    @property
    def kind(self) -> str:
        return self._kind

    def build(self, parameters: FeatureParameters) -> CandleIndicatorFeature:
        indicator = INDICATORS[self._kind](
            parameters.integer("period"),
            column=parameters.text("column", "close"),
        )
        return CandleIndicatorFeature(indicator)
