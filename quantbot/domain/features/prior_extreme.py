# quantbot/domain/features/prior_extreme.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class PriorExtreme:
    """過去 N 根的最高價（或最低價），**保證不含當根**。實作 domain 的 Feature。

    這是全系列第二次正式處理未來函數，而它的形狀跟 Day 04 那次不一樣。Day 04 的
    問題是「用當根收盤價的訊號假設能用當根開盤價成交」；這裡的問題更隱蔽：

        candles["high"].rolling(20).max()

    這一行算出來的「前 20 根最高價」**包含當根自己**。於是「當根的高點突破前高」
    這個條件永遠不會成立——因為當根的高點本來就是那個最大值的候選之一，
    它最多只能等於前高，不可能大於。

    症狀不是「訊號變少」，是**訊號完全消失**，而程式不會有任何異常。這種錯誤比
    算錯數字更難察覺，因為輸出是一個空的訊號序列，看起來像「這段行情沒有突破」。

    所以 shift(1) 寫在這個類別裡，而且它是這個類別存在的唯一理由。任何要用「前高」
    的地方 MUST 走這裡，NEVER 自己寫 rolling().max()。
    """

    def __init__(self, *, side: ExtremeSide, window: int = 20) -> None:
        if window < 1:
            raise ValueError(f"window 必須 >= 1，收到 {window}")
        self.side = side
        self.window = window

    @property
    def name(self) -> str:
        return f"prior_{self.side}_{self.window}"

    @property
    def warmup_bar_count(self) -> int:
        """視窗滿了才有值，而且因為 shift(1)，第一個有值的位置再往後一根。"""
        return self.window

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        values = view.candles.frame[self.side.column].astype("float64")
        # 先 shift 再 rolling，兩者順序在數學上等價，但先 shift 讀起來更接近
        # 「拿前一根之前的資料算」這句話，也不會有人誤以為 rolling 之後還要再挪
        return self.side.rolling_extreme(values.shift(1), self.window).rename(self.name)


def parse_extreme_side(parameters: FeatureParameters) -> ExtremeSide:
    """設定檔的 side 字串轉 ExtremeSide。

    三個 builder 共用它（前高、突破、流動性擺盪），所以它是模組層級的函式而不是
    某個 builder 的方法——它不屬於其中任何一個。
    """
    raw = parameters.text("side", ExtremeSide.HIGH.value)
    if raw not in tuple(ExtremeSide):
        raise ValueError(
            f"side 只能是 {[value.value for value in ExtremeSide]}，實得 {raw!r}"
        )
    return ExtremeSide(raw)


class PriorExtremeBuilder:
    """設定檔的 prior_extreme。"""

    @property
    def kind(self) -> str:
        return "prior_extreme"

    def build(self, parameters: FeatureParameters) -> PriorExtreme:
        return PriorExtreme(
            side=parse_extreme_side(parameters),
            window=parameters.integer("window", 20),
        )
