# quantbot/domain/features/average_true_range.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.indicators.rsi import WilderSmoother
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class ATR:
    """平均真實區間。實作 domain 的 Feature，**不是** Day 04 的 Indicator。

    為什麼不是 Indicator：那個 ABC 的契約是「吃一個欄位、回一條序列」，`compute()`
    會先把 `self.column` 取出來轉成 float64 再交給子類別。ATR 需要高、低、收三欄，
    契約裝不下它。這不是分類學上的爭論——真的寫下去就會發現要嘛破壞 Indicator 的
    契約，要嘛在 ATR 裡繞過基底類別，兩種都比「它是另一種東西」糟。

    真實區間取三者的最大值，第三項是它跟「高減低」的差別所在：

        TR = max(高 − 低, |高 − 前收|, |低 − 前收|)

    後兩項處理的是**跳空**：如果這一根整根跳到前一根之上，「高 − 低」可能很小，
    但實際的價格移動很大。加密貨幣 24/7 不休市，跳空比股市少得多，但快速行情裡
    一分鐘跳 1% 的事還是會發生，那時候只看「高 − 低」會低估波動。

    ATR 是 Day 24 決定停損距離的依據，所以它算出來的單位很重要：它是**價格單位**，
    不是百分比。跨交易對比較時要自己除以價格。
    """

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError(f"period 必須 >= 1，收到 {period}")
        self.period = period
        self._smoother = WilderSmoother(period)

    @property
    def name(self) -> str:
        return f"atr_{self.period}"

    @property
    def warmup_bar_count(self) -> int:
        """跟 RSI 一樣：真實區間的第一筆沒有定義，遞迴從第 period + 1 根開始。"""
        return self.period

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        return self._smoother.smooth(self.true_range(view.candles.frame)).rename(
            self.name
        )

    @staticmethod
    def true_range(candles: pd.DataFrame) -> pd.Series:
        """三個候選取最大值，全部向量化。

        第 0 筆是 NaN 而不是「高 − 低」：沒有前一根的收盤價，所以那兩個跳空項
        沒有定義。填成「高 − 低」會讓第一根的 TR 系統性偏小，而那個偏差會被
        Wilder 平滑一路帶進暖機期。WilderSmoother 的輸入慣例正是第 0 筆為 NaN。
        """
        previous_close = candles["close"].shift(1)
        candidates = pd.concat(
            {
                "high_low": candles["high"] - candles["low"],
                "high_close": (candles["high"] - previous_close).abs(),
                "low_close": (candles["low"] - previous_close).abs(),
            },
            axis=1,
        )
        # skipna=False 是必要的：第 0 筆只有 high_low 有值，用預設的 skipna=True
        # 會挑出那個值，於是第 0 筆變成「高 − 低」而不是 NaN
        return candidates.max(axis=1, skipna=False).rename("true_range")
