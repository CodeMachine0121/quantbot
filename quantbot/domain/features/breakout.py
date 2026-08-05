# quantbot/domain/features/breakout.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.features.prior_extreme import PriorExtreme, parse_extreme_side
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class Breakout:
    """突破事件：這一根的高點有沒有超過前高（或低點跌破前低）。實作 domain 的 Feature。

    它是這個系列第一個**事件式**特徵，跟前面所有特徵的形狀不同。前面那些每一根都
    有一個連續的值（RSI 是 43.2、OBI 是 −0.17）；這一個絕大多數時候是 0，偶爾是 1。

    這個差別會一路影響到後面：

    - 統計上：事件稀疏，所以樣本數少得多。一年的 1 小時線有 8,760 根，其中突破
      可能只有幾百次。Day 21 會處理「樣本數少讓回測的統計意義變薄」這件事。
    - 介面上：它照樣回傳一條與 K 線等長、index 相同的序列（只是值是 0 與 1），
      所以它不需要特別的介面。**事件不是另一種型別，是另一種取值。**

    輸出用 float64 的 0.0／1.0 而不是 bool：Day 15 的管線會把所有特徵 concat 成
    一張表，混入 bool 欄位會讓那張表的 dtype 變成 object，而 object 欄位的算術
    運算會慢一個數量級，也不再支援 NaN 表達暖機期。
    """

    def __init__(self, *, side: ExtremeSide, window: int = 20) -> None:
        self._prior = PriorExtreme(side=side, window=window)
        self.side = side
        self.window = window

    @property
    def name(self) -> str:
        return f"breakout_{self.side}_{self.window}"

    @property
    def warmup_bar_count(self) -> int:
        return self._prior.warmup_bar_count

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        return self.events(view).astype("float64").rename(self.name)

    def prior_level(self, view: MarketView) -> pd.Series:
        """突破判斷用的門檻本身。

        圖表要畫這條線，而它 MUST 跟判斷用的是同一份計算——各算一次的話，
        圖上的線與標記的位置會在某些邊界上對不起來，而那種不一致最難查。
        """
        return self._prior.compute(view)

    def events(self, view: MarketView) -> pd.Series:
        """哪幾根發生了突破。回傳 boolean，暖機期是 False 而不是 NaN。

        boolean 沒辦法表達「還不知道」，所以暖機期在這裡是 False——那是正確的語意：
        前 20 根確實沒有發生突破事件（我們不知道有沒有，而不知道就不能算發生）。
        真正需要區分「沒發生」與「不知道」的地方是 compute()，它輸出的 NaN 由
        prior_extreme 的 NaN 傳遞下來。
        """
        candles = view.candles.frame
        threshold = self._prior.compute(view)
        return self.side.breaks(candles[self.side.column].astype("float64"), threshold)

    def excess(self, view: MarketView) -> pd.Series:
        """突破了多少，以價格單位表示。沒突破的那幾根是 0。

        「突破 0.3 USDT」與「突破 300 USDT」是完全不同的事件，而 events() 把它們
        當成同一件事。這個量在 Day 13 的統計裡用來檢驗「勉強擦過去的突破是不是
        比較容易失敗」。
        """
        candles = view.candles.frame
        threshold = self._prior.compute(view)
        values = candles[self.side.column].astype("float64")
        distance = (
            values - threshold if self.side is ExtremeSide.HIGH else threshold - values
        )
        return distance.clip(lower=0.0).rename(f"{self.name}_excess")


class BreakoutBuilder:
    """設定檔的 breakout。"""

    @property
    def kind(self) -> str:
        return "breakout"

    def build(self, parameters: FeatureParameters) -> Breakout:
        return Breakout(
            side=parse_extreme_side(parameters),
            window=parameters.integer("window", 20),
        )
