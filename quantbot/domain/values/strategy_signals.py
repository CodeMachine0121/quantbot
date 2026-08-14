# quantbot/domain/values/strategy_signals.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.strategies.strategy import Strategy


@dataclass(frozen=True)
class StrategySignals:
    """一次訊號計算的完整結果：三棵樹各自的原始判斷，加上引擎解出來的部位。

    為什麼要把原始判斷留著，而不只回傳部位：因為「進場訊號 240 次，實際交易 232 筆」
    這個差距是唯一能看出過濾條件與狀態機做了什麼的地方。只回部位的話，一個從來
    不成立的條件與一個被過濾光的條件長得一模一樣。

    行情資料不轉 DTO（Day 15 的決定），這裡沿用同一條：主體是 DataFrame 與 Series，
    每跨一層轉一次形狀是純儀式。所以它是值，不是報告 DTO。
    """

    strategy: Strategy
    table: pd.DataFrame
    entry_signals: pd.Series
    exit_signals: pd.Series
    allowed: pd.Series
    positions: pd.Series

    @property
    def bar_count(self) -> int:
        return len(self.table)

    @property
    def held_bar_count(self) -> int:
        return int((self.positions != 0.0).sum())

    @property
    def exposure(self) -> float:
        """有部位的根數佔總根數的比例。空表回 0，不丟例外。"""
        if self.bar_count == 0:
            return 0.0
        return self.held_bar_count / self.bar_count

    @property
    def trade_count(self) -> int:
        """交易筆數＝部位從 0 變成非 0 的次數。

        第一根要算進去：一個從第一根就持有的策略（BuyAndHold 在位移之後是第二根）
        也是一筆交易。用 diff() 的話第一根是 NaN，所以這裡拿前一根補 0 的版本比。
        """
        previous = self.positions.shift(1, fill_value=0.0)
        return int(((self.positions != 0.0) & (previous == 0.0)).sum())

    @property
    def entry_signal_count(self) -> int:
        return int(self.entry_signals.sum())

    @property
    def vetoed_entry_count(self) -> int:
        """被過濾條件否決掉的進場訊號有幾根。

        它跟「少了幾筆交易」不是同一個數字：被否決的訊號有可能發生在已經持有部位
        的時候，那種本來也不會產生新交易。兩個數字都要看得到，才說得清過濾條件
        到底改變了什麼。
        """
        return int((self.entry_signals & ~self.allowed).sum())
