# quantbot/domain/values/market_view.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market_input import MarketInput


@dataclass(frozen=True)
class MarketView:
    """一次特徵計算的所有原料。

    為什麼不是「每個特徵各自宣告要吃 DataFrame 還是 CandleSeries」：那樣的話每加
    一種資料，所有特徵的簽章都要跟著改一次。這裡把「有哪些資料」收成一個值，
    特徵的簽章就固定了，而它們用 require_* 取自己要的那份。

    K 線是必要的，因為它定義了**輸出的索引**。掛單簿與逐筆成交的索引是不規則的，
    要跟策略對得起來就必須對齊到某個共同的時間軸，而那個時間軸只能是 K 線。
    """

    candles: CandleSeries
    trades: TradeSeries | None = None
    depth: DepthSeries | None = None

    @property
    def instrument(self) -> Instrument:
        return self.candles.instrument

    def available_inputs(self) -> frozenset[MarketInput]:
        available = {MarketInput.CANDLES}
        if self.trades is not None and not self.trades.is_empty():
            available.add(MarketInput.TRADES)
        if self.depth is not None and not self.depth.is_empty():
            available.add(MarketInput.DEPTH)
        return frozenset(available)

    def missing_inputs(
        self, required: frozenset[MarketInput]
    ) -> frozenset[MarketInput]:
        return required - self.available_inputs()

    def strategy_table(self, features: pd.DataFrame) -> pd.DataFrame:
        """條件要吃的那張表：K 線的欄位 ＋ 算好的特徵。

        兩者併在一起是刻意的。價格不是特徵——它是原料——但條件要拿收盤價跟 VWAP
        比大小，所以它必須在同一張表裡，而且用 `close` 這個名字，不是某個假特徵的
        名字。

        對齊方向是「K 線對齊到特徵表」：特徵表已經切掉暖機期，所以它比 K 線短，
        而反過來對齊會把暖機期的 NaN 放回來。
        """
        candles = self.candles.frame.reindex(features.index)
        return pd.concat([candles, features], axis=1)

    def require_trades(self) -> TradeSeries:
        if self.trades is None or self.trades.is_empty():
            raise ValueError("這個特徵需要逐筆成交，但 MarketView 裡沒有")
        return self.trades

    def require_depth(self) -> DepthSeries:
        """缺掛單簿時丟 ValueError 而不是回空的。

        回空的話後面會算出一整欄 NaN，而 NaN 在這個系列裡的意思是「暖機期還沒到」。
        兩件事都用 NaN 表達，就再也分不出「資料沒錄到」與「資料還不夠」。
        """
        if self.depth is None or self.depth.is_empty():
            raise ValueError("這個特徵需要掛單簿深度摘要，但 MarketView 裡沒有")
        return self.depth
