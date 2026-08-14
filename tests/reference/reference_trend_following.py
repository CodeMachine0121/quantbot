# tests/reference/reference_trend_following.py
"""趨勢跟隨策略的「最直白的 Python 寫法」，只在測試裡當對照組。

它是 Day 17 開頭那段沒有任何抽象的實作：條件寫死、位移寫在算式裡、狀態機是一個
一根一根跑的迴圈。它 NEVER 進正式路徑，價值在於**它跟積木版本必須逐根相同**——
兩者一旦分岔，就表示引擎或載入器其中一個理解錯了。

它吃的是已經算好的特徵表，所以比對的是「策略邏輯」而不是「指標算法」。
指標本身的對照組在 tests/reference/reference_ema.py 與 reference_rsi.py。
"""

from __future__ import annotations

import pandas as pd


class ReferenceTrendFollowing:
    """EMA 快慢線交叉進出、RSI 擋掉追高，一根一根跑完。"""

    def __init__(
        self,
        *,
        fast: str = "ema_12",
        slow: str = "ema_26",
        momentum: str = "rsi_14",
        overbought: float = 70.0,
    ) -> None:
        self.fast = fast
        self.slow = slow
        self.momentum = momentum
        self.overbought = overbought

    def positions(self, table: pd.DataFrame) -> pd.Series:
        """回傳每一根的部位（1.0 持有、0.0 空手）。"""
        fast = table[self.fast]
        slow = table[self.slow]
        ready = fast.notna() & slow.notna()
        above = (fast > slow) & ready

        # 交叉＝狀態翻轉，而且前一根也必須是有效值
        golden = (
            above & ~above.shift(1, fill_value=False) & ready.shift(1, fill_value=False)
        )
        death = ~above & above.shift(1, fill_value=False) & ready

        # 追高的過濾：交叉當下 RSI 已經超買就不進
        overheated = table[self.momentum] > self.overbought
        entry = (golden & ~overheated).shift(1, fill_value=False)
        leave = death.shift(1, fill_value=False)

        # 交叉條件要看前一根，加上位移一根，所以最快在第 2 根才能持有
        first_allowed_bar = 2

        held: list[float] = []
        holding = False
        for position, moment in enumerate(table.index):
            if holding and bool(leave[moment]):
                holding = bool(entry[moment])
            elif not holding and position >= first_allowed_bar and bool(entry[moment]):
                holding = True
            held.append(1.0 if holding else 0.0)

        return pd.Series(held, index=table.index, dtype="float64")
