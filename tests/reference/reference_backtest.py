# tests/reference/reference_backtest.py
"""逐根模擬的回測，只在測試裡當對照組。

它是事件驅動引擎（Backtrader 那一類）的做法：一根一根往前走，維護一個狀態。
向量化的版本一次算完整段，兩者的數字必須逐根相同——如果不同，錯的幾乎一定是
向量化那邊，因為這一份跟讀起來的算式一模一樣。

它 NEVER 進正式路徑。它慢，而 Day 21 要跑幾百個組合。
"""

from __future__ import annotations

import pandas as pd


class ReferenceBacktest:
    """一根一根滾出權益曲線。"""

    def __init__(
        self, *, initial_capital: float = 10_000.0, one_way_rate: float = 0.0
    ) -> None:
        self.initial_capital = initial_capital
        self.one_way_rate = one_way_rate

    def equity(self, positions: pd.Series, close: pd.Series) -> pd.Series:
        """回傳權益曲線，index 與輸入相同。"""
        capital = self.initial_capital
        previous_position = 0.0
        previous_price = float(close.iloc[0]) if len(close) else 0.0
        curve: list[float] = []

        for moment in positions.index:
            price = float(close[moment])
            position = float(positions[moment])

            price_return = (
                0.0 if previous_price == 0.0 else price / previous_price - 1.0
            )
            turnover = abs(position - previous_position)
            # 先付換倉的成本，剩下的錢才承受這一根的漲跌
            capital *= 1.0 - turnover * self.one_way_rate
            capital *= 1.0 + position * price_return

            curve.append(capital)
            previous_position = position
            previous_price = price

        return pd.Series(curve, index=positions.index, dtype="float64")
