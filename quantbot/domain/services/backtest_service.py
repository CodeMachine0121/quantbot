# quantbot/domain/services/backtest_service.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.strategy_signals import StrategySignals


class BacktestService:
    """部位序列 ＋ 收盤價 → 權益曲線與交易明細。

    整段模擬只有四行算式，而它之所以這麼短，是因為 Day 16 把部位序列的時間語意
    釘死了：`positions[t]` 是「第 t 根整根都持有」，成交發生在第 t-1 根的收盤。
    所以「這一根的策略報酬」就是部位乘上這一根的價格報酬，兩邊講的是同一段時間，
    不必再對齊一次。

    它是向量化的（一次算完整段，不是逐根模擬），這跟前面十八天的資料處理一脈相承。
    逐根模擬的引擎（Backtrader 那一類）能表達更多東西——限價單、部分成交、
    多資產的資金分配——代價是慢好幾個數量級，而 Day 21 要跑幾百個組合。
    tests/reference/reference_backtest.py 有一份逐根的實作當對照組，兩者必須逐根相同。

    成本用**換手**計價：`|position[t] - position[t-1]|` 是這一根換了多少倉，乘上單邊
    成本率就是這一根付的錢。這個寫法自動處理了「連續持有不必付錢」與「進場出場
    各付一次」，不必去數交易筆數。
    """

    def run(
        self,
        signals: StrategySignals,
        specification: BacktestSpecification,
        *,
        trial_count: int = 1,
    ) -> BacktestReportDto:
        if trial_count < 1:
            raise ValueError(f"trial_count 必須 >= 1，收到 {trial_count}")

        close = signals.table["close"].astype("float64")
        positions = signals.positions
        price_returns = close.pct_change().fillna(0.0)

        gross_returns = positions * price_returns
        turnover = (positions - positions.shift(1, fill_value=0.0)).abs()
        cost_returns = turnover * specification.costs.one_way_rate
        # 成本是**乘**上去的，不是減掉的：換倉發生在前一根的收盤，付掉成本之後
        # 剩下的錢才去承受這一根的漲跌。寫成 (1 + r) - c 會多算一個 c × r 的二階項，
        # 數字上很小，但那樣就跟現成的回測引擎對不起來（見測試）。
        net_growth = (1.0 - cost_returns) * (1.0 + gross_returns)
        net_returns = net_growth - 1.0

        equity = specification.initial_capital * net_growth.cumprod()
        gross_equity = specification.initial_capital * (1.0 + gross_returns).cumprod()
        trades = self._trades(positions, close, specification)

        return BacktestReportDto(
            strategy_name=signals.strategy.name,
            bar_count=len(positions),
            trade_count=len(trades),
            trial_count=trial_count,
            initial_capital=specification.initial_capital,
            costs=specification.costs,
            equity=equity.rename("equity"),
            gross_equity=gross_equity.rename("gross_equity"),
            returns=net_returns.rename("returns"),
            trades=trades,
            turnover=float(turnover.sum()),
            cost_paid=float(
                (
                    equity.shift(1).fillna(specification.initial_capital) * cost_returns
                ).sum()
            ),
        )

    @staticmethod
    def _trades(
        positions: pd.Series,
        close: pd.Series,
        specification: BacktestSpecification,
    ) -> pd.DataFrame:
        """把部位序列拆成一筆一筆交易。

        兩個容易錯的地方：

        - **進場價是前一根的收盤價。** `positions[t]` 為 1 代表在第 t-1 根收盤時
          成交，所以拿第 t 根的收盤價當進場價會少算（或多算）一根的漲跌，而那個
          誤差剛好是策略最想看到的方向。
        - **回測結束時還開著的部位要算進來。** 它的出場價是最後一根的收盤價。
          漏掉它會讓最後一筆交易憑空消失，而那一筆常常是最大的一筆。
        """
        held = (positions != 0.0).to_numpy()
        if not held.any():
            return pd.DataFrame(
                columns=[
                    "opened_at",
                    "closed_at",
                    "bars_held",
                    "entry_price",
                    "exit_price",
                    "gross_return",
                    "net_return",
                ]
            )

        previous = np.concatenate(([False], held[:-1]))
        starts = np.flatnonzero(held & ~previous)
        ends = np.flatnonzero(~held & previous)
        if ends.size < starts.size:
            # 最後一筆還開著：出場落在資料的盡頭
            ends = np.concatenate((ends, [held.size]))

        prices = close.to_numpy()
        moments = pd.DatetimeIndex(positions.index)
        entry_prices = prices[starts - 1]
        exit_prices = prices[ends - 1]
        gross = exit_prices / entry_prices - 1.0

        return pd.DataFrame(
            {
                "opened_at": moments[starts],
                "closed_at": moments[np.minimum(ends, held.size - 1)],
                "bars_held": ends - starts,
                "entry_price": entry_prices,
                "exit_price": exit_prices,
                "gross_return": gross,
                "net_return": gross - specification.costs.round_trip_rate,
            }
        )
