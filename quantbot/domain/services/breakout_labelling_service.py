# quantbot/domain/services/breakout_labelling_service.py
from __future__ import annotations

from typing import ClassVar

import pandas as pd

from quantbot.domain.features.breakout import Breakout
from quantbot.domain.values.breakout_label import BreakoutLabel
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.market_view import MarketView


class BreakoutLabellingService:
    """給每次突破貼上「守住了」或「被打回來」。

    **這個 service 一定會用到未來資料，而那是它的工作。** 它產出的是標籤，不是特徵，
    所以它 NEVER 出現在策略路徑上——只出現在分析與統計裡。這個界線在程式碼裡的
    表現方式是：它回傳的東西不叫 feature、不實作 Feature 協定，也不進特徵註冊表。

    定義只有一句：突破之後 horizon 根之內，價格有沒有跌回**被突破的那個價位**。

    「被突破的價位」是前高（前低），不是突破那根 K 線自己的高點。這個選擇很重要：
    用那根 K 線的高點當基準的話，只要之後沒有繼續往上就算失敗，那個定義太嚴，
    也不對應任何人的實際處境——在前高掛突破單的人，成本是前高。

    刻意用這個最粗的定義，理由是它不需要挑任何門檻參數。「走了多遠算真突破」需要
    一個數字（幾個 ATR？幾個百分點？），而那個數字一挑，統計結果就開始取決於它。
    先用不需要參數的定義得到一個基準數字，再談要不要細分。
    """

    LABEL_COLUMN: ClassVar[str] = "label"
    FAVOURABLE_COLUMN: ClassVar[str] = "favourable_excursion"
    ADVERSE_COLUMN: ClassVar[str] = "adverse_excursion"

    def __init__(self, *, horizon: int = 10) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必須 >= 1，收到 {horizon}")
        self._horizon = horizon

    @property
    def horizon(self) -> int:
        return self._horizon

    def label(self, view: MarketView, breakout: Breakout) -> pd.DataFrame:
        """回傳只有突破那幾根的表：標籤 ＋ 期間的順逆行幅度。

        favourable_excursion 與 adverse_excursion 是「突破之後最多往有利／不利
        的方向走了多少」，以價格單位表示。它們是這張表裡最有資訊的兩欄——
        只知道「守住 62%」不足以判斷值不值得做，還要知道守住的時候賺多少、
        被打回來的時候賠多少。
        """
        candles = view.candles.frame
        events = breakout.events(view)
        level = breakout.prior_level(view)

        forward_high = self._forward_extreme(candles["high"], ExtremeSide.HIGH)
        forward_low = self._forward_extreme(candles["low"], ExtremeSide.LOW)

        if breakout.side is ExtremeSide.HIGH:
            failed = forward_low < level
            favourable = forward_high - level
            adverse = level - forward_low
        else:
            failed = forward_high > level
            favourable = level - forward_low
            adverse = forward_high - level
        # 兩個幅度都夾在 0 以上：一次完全沒有回檔的突破，逆行幅度是 0 而不是負數，
        # 而負數會讓「逆行幅度的中位數」這個統計量變得沒辦法解讀
        favourable = favourable.clip(lower=0.0)
        adverse = adverse.clip(lower=0.0)

        table = pd.DataFrame(
            {
                self.LABEL_COLUMN: failed.map(
                    {True: BreakoutLabel.FAILED.value, False: BreakoutLabel.HELD.value}
                ),
                self.FAVOURABLE_COLUMN: favourable,
                self.ADVERSE_COLUMN: adverse,
            }
        )
        # 只留突破那幾根，並丟掉窗口不完整的尾巴（最後 horizon 根還沒有未來）
        return table.loc[events & forward_high.notna() & forward_low.notna()]

    def _forward_extreme(self, values: pd.Series, side: ExtremeSide) -> pd.Series:
        """接下來 horizon 根的極值，**不含當根**。

        寫法是「反轉序列、往前 rolling、再反轉回來」。直覺的寫法是
        rolling(horizon).max().shift(-horizon)，但那個 shift 的格數很容易差一格，
        而差一格的症狀是標籤系統性偏向某一邊——那種偏差在統計結果上看不出來。
        """
        reversed_values = values.astype("float64").iloc[::-1]
        extreme = side.rolling_extreme(reversed_values.shift(1), self._horizon)
        return extreme.iloc[::-1]
