# quantbot/domain/strategies/strategy_engine.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.values.holding_rules import HoldingRules


class StrategyEngine:
    """把一個策略與一張特徵表變成一條部位序列。

    它只有一個對外方法，而它擔保三件事——這三件事一旦交給每個策略各自記得，
    策略數量一多就一定會有人漏掉其中一個：

    1. **訊號位移。** 第 t 根的條件只用得到第 t 根收盤時已知的資訊，所以最快在
       第 t+1 根才能持有。這是 Day 04 講的未來函數，而它在這裡被做成引擎的行為，
       不是策略的責任。
    2. **暖機期。** 條件樹宣告的暖機期加上位移的根數，那幾根一律不持有。
    3. **時間規則。** 最大持有根數與冷卻期，見 HoldingRules。

    signal_delay_bars 預設 1，也就是「第 t 根的資訊、第 t+1 根成交」。它是可設的
    參數而不是寫死的常數，唯一的理由是 Day 19 要用 0 示範未來函數會讓報酬離譜到
    什麼程度。實際用途一律是 1；設成 0 的回測結果不能當結論看。
    """

    def __init__(self, *, signal_delay_bars: int = 1) -> None:
        if signal_delay_bars < 0:
            raise ValueError(f"signal_delay_bars 不能是負數，收到 {signal_delay_bars}")
        self._signal_delay_bars = signal_delay_bars

    @property
    def signal_delay_bars(self) -> int:
        return self._signal_delay_bars

    def positions(self, strategy: Strategy, table: pd.DataFrame) -> pd.Series:
        """回傳每一根的部位權重，index 與輸入的表完全相同。

        1.0 代表這一根**整根都持有**（在前一根收盤時成交），0.0 代表空手。
        回測因此可以直接把它乘上「這一根的報酬」，兩邊的時間語意是對齊的。
        """
        entries = self._delayed(
            strategy.entry.evaluate(table) & strategy.filters.evaluate(table)
        )
        exits = self._delayed(strategy.exit.evaluate(table))
        blocked_until = strategy.warmup_bar_count + self._signal_delay_bars

        held = self._resolve_holdings(
            entries.to_numpy(dtype=bool),
            exits.to_numpy(dtype=bool),
            strategy.holding,
            first_allowed_bar=blocked_until,
        )
        return pd.Series(
            held * strategy.direction.weight,
            index=table.index,
            dtype="float64",
            name=f"position_{strategy.name}",
        )

    def _delayed(self, signal: pd.Series) -> pd.Series:
        """位移只發生在這裡，整個專案沒有第二個地方會做這件事。"""
        if self._signal_delay_bars == 0:
            return signal
        return signal.shift(self._signal_delay_bars, fill_value=False)

    @staticmethod
    def _resolve_holdings(
        entries: np.ndarray,
        exits: np.ndarray,
        holding: HoldingRules,
        *,
        first_allowed_bar: int,
    ) -> np.ndarray:
        """把進出場訊號解成「哪幾根在持有」。

        這是全系列唯一一個帶迴圈的計算路徑，所以要說清楚為什麼：**這裡的狀態
        依賴自己的輸出。** 「這根能不能進場」取決於手上有沒有部位，而那取決於
        前面哪一根進場、又在哪一根出場——一個純粹的欄位運算算不出依賴自身結果的
        東西。加上最大持有根數與冷卻期之後更是如此。

        但迴圈的長度不是 K 線數，是**交易筆數**。searchsorted 每次直接跳到下一個
        合法的進場位置，所以 13,848 根 K 線上跑一個交易幾十次的策略，這個迴圈就
        轉幾十次。Day 04 那條「NEVER 用 for loop 遍歷 K 線」的規矩沒有被打破。

        同一根同時出現進場與出場訊號時，**進場勝出，出場最快在下一根**。這個決定
        讓每一筆交易至少持有一根，也讓這個迴圈一定會前進。
        """
        held = np.zeros(entries.size, dtype=bool)
        if entries.size == 0:
            return held

        entry_bars = np.flatnonzero(entries)
        exit_bars = np.flatnonzero(exits)
        cooldown = holding.cooldown_bars or 0
        cursor = first_allowed_bar

        while True:
            candidate = int(np.searchsorted(entry_bars, cursor, side="left"))
            if candidate >= entry_bars.size:
                return held

            opened_at = int(entry_bars[candidate])
            closed_at = StrategyEngine._closing_bar(
                exit_bars, opened_at, holding.maximum_holding_bars, entries.size
            )
            held[opened_at:closed_at] = True
            cursor = closed_at + cooldown

    @staticmethod
    def _closing_bar(
        exit_bars: np.ndarray,
        opened_at: int,
        maximum_holding_bars: int | None,
        bar_count: int,
    ) -> int:
        """這一筆在第幾根結束持有（不含該根）。

        三個候選取最小的：出場條件成立的第一根、抱滿最大根數的那一根、
        以及資料的盡頭。最後一個代表回測結束時還開著的部位——它一定要被算進去，
        否則最後一筆交易會憑空消失，而那筆常常是最大的一筆。
        """
        following = int(np.searchsorted(exit_bars, opened_at, side="right"))
        by_condition = (
            int(exit_bars[following]) if following < exit_bars.size else bar_count
        )
        if maximum_holding_bars is None:
            return min(by_condition, bar_count)
        return min(by_condition, opened_at + maximum_holding_bars, bar_count)
