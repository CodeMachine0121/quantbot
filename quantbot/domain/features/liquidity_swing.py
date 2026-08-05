# quantbot/domain/features/liquidity_swing.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.trade_columns import TradeColumns


class LiquiditySwing:
    """被突破那一側的流動性減少了，是**被吃掉**還是**被撤走**。實作 domain 的 Feature。

    這是今天唯一需要三種原料的特徵（K 線、逐筆成交、掛單簿），而它問的問題是
    Day 10 那個限制的正面回答：掛單可以撤，所以光看掛單簿少了多少不知道發生什麼事。
    把它跟成交量對起來就分得出來：

        吃掉的比例 = 同期間該方向的 taker 成交量 / 該側深度的減少量

    - 接近 1：掛單是被真的成交吃掉的。有人用真錢把它買走了。
    - 接近 0：掛單消失了但沒有成交。它被撤單了。

    兩者在價格圖上長得一樣（深度都變薄、價格都往上），但意義相反。被吃掉代表有
    真實的買盤；被撤走代表掛單的人只是把單子拿走，那個「上漲」沒有任何人付錢。

    值域不封閉在 0 到 1：同一段時間裡可能有人一邊吃、一邊有新單補上，於是分母
    （淨減少量）比分子（成交量）小很多，比例會大於 1。那不是錯誤，那是「掛單補得
    比吃得快」，本身就是資訊，所以 NEVER 把它 clip 到 1。
    """

    def __init__(self, *, side: ExtremeSide, window_seconds: float = 5.0) -> None:
        if window_seconds <= 0:
            raise ValueError(f"window_seconds 必須大於 0，收到 {window_seconds}")
        self.side = side
        self.window_seconds = window_seconds

    @property
    def name(self) -> str:
        return f"liquidity_swing_{self.side}_{self.window_seconds:g}s"

    @property
    def warmup_bar_count(self) -> int:
        """它不看 K 線的歷史，只看每根 K 線內部的掛單簿與成交，所以不用暖機。"""
        return 0

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES, MarketInput.TRADES, MarketInput.DEPTH})

    def compute(self, view: MarketView) -> pd.Series:
        """對齊到 K 線：每根取那一根期間內的比例中位數。

        用中位數而不是平均：這個比例偶爾會出現非常大的值（分母接近 0），
        平均會被那幾筆主導。
        """
        ratio = self.consumed_ratio(view)
        timeframe = view.candles.instrument.timeframe
        aligned = ratio.resample(
            timeframe.pandas_frequency, label="left", closed="left"
        ).median()
        return aligned.reindex(view.candles.open_times).rename(self.name)

    def consumed_ratio(self, view: MarketView) -> pd.Series:
        """原始取樣頻率下的比例，index 是掛單簿的取樣時間。"""
        depth = view.require_depth()
        trades = view.require_trades()
        window = f"{self.window_seconds}s"

        reduction = self._depth_reduction(depth.frame, window)
        volume = self._sampled_at(
            self._taker_volume(trades.frame, window), depth.captured_times
        )
        # 深度沒有減少（或反而增加）的時候這個問題沒有意義，回 NaN 而不是 0
        return (volume / reduction.where(reduction > 0)).rename(self.name)

    @staticmethod
    def _sampled_at(values: pd.Series, moments: pd.DatetimeIndex) -> pd.Series:
        """把成交那一側的累積量取樣到掛單簿的時間點上。

        這裡 NEVER 用 reindex(method="ffill")：**成交的時間戳不是唯一的**（同一個
        毫秒裡有幾十筆成交是常態，Day 09 量過每分鐘中位數 368 列），而 reindex 在
        有重複索引的軸上會直接丟 ValueError。

        merge_asof 才是「取此刻或之前最近的那一個值」這件事的工具，而且它接受
        重複的鍵。它要求兩邊都已排序，這由 TradeSeries 與 DepthSeries 的建構保證。
        """
        left = pd.DataFrame({"moment": moments})
        right = pd.DataFrame(
            {"moment": pd.DatetimeIndex(values.index), "value": values.to_numpy()}
        )
        merged = pd.merge_asof(left, right, on="moment", direction="backward")
        return pd.Series(
            merged["value"].to_numpy(), index=moments, name=str(values.name)
        )

    def _depth_reduction(self, depth: pd.DataFrame, window: str) -> pd.Series:
        """被突破那一側的深度在這段視窗內淨減少多少。

        突破前高看的是**賣方**的深度（要往上走就得吃掉賣單），突破前低看買方。
        這個對應寫反的話，算出來的比例還是一個合理的數字，只是它描述的是
        完全無關的另一側。
        """
        column = (
            DepthColumns.ask_quantity(DepthColumns.LEVELS[-1])
            if self.side is ExtremeSide.HIGH
            else DepthColumns.bid_quantity(DepthColumns.LEVELS[-1])
        )
        quantity = depth[column]
        return quantity.rolling(window).max() - quantity

    def _taker_volume(self, trades: pd.DataFrame, window: str) -> pd.Series:
        """這段視窗內、往突破方向的 taker 成交量。

        往上突破要看主動買（buyer_is_maker 為 False），往下看主動賣。
        """
        taker_buy = ~trades[TradeColumns.BUYER_IS_MAKER]
        wanted = taker_buy if self.side is ExtremeSide.HIGH else ~taker_buy
        directional = trades[TradeColumns.QUANTITY].where(wanted, 0.0)
        return directional.rolling(window).sum()
