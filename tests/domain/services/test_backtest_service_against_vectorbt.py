"""跟 VectorBT 對數字。

前一個測試（reference_backtest）驗的是「向量化跟逐根模擬算出同一件事」，也就是
自己的實作內部一致。這一個驗的是另一個問題：**我們對「回測」的定義跟業界主流引擎
是不是同一件事。** 兩個問題都要問——一份自己跟自己一致、但語意跟所有人都不同的
回測，數字再穩定也沒有意義。

殘差不是零，而那個殘差本身是這個測試最有價值的產出，見下面的說明。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import vectorbt as vbt

from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.strategies.condition import Condition
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.cost_model import CostModel

INITIAL_CAPITAL = 10_000.0
FEE_RATE = 0.001


class Flags(Condition):
    def __init__(self, name: str, flags: list[bool]) -> None:
        self._name = name
        self._flags = flags

    @property
    def name(self) -> str:
        return self._name

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset()

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return pd.Series(self._flags, index=table.index)


def test_our_equity_agrees_with_vectorbt_to_within_the_fee_convention():
    """滑價設 0，因為兩邊對滑價的模型不同（我們扣比例，VectorBT 調整成交價）。

    剩下的差異只有一件事：全額買進時手續費從哪裡扣。我們用 (1 - f)，VectorBT 用
    1 / (1 + f)——兩者差在 f² 的量級，每一筆交易累積一次。所以誤差會隨交易筆數
    成長，而它的方向是固定的：我們的數字比較保守。

    這個測試因此不追求逐根相同，它要確認的是三件事：交易筆數完全一樣、
    報酬差在 f² 的量級、而且差的方向是保守的那一邊。
    """
    generator = np.random.default_rng(19)
    bar_count = 500
    prices = 100.0 * np.exp(np.cumsum(generator.normal(0.0, 0.01, bar_count)))
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    table = pd.DataFrame({"close": prices}, index=index)

    strategy = Strategy(
        name="agreement",
        entry=Flags("entry", list(generator.uniform(size=bar_count) < 0.05)),
        exit=Flags("exit", list(generator.uniform(size=bar_count) < 0.05)),
    )
    signals = StrategyEngine().signals(strategy, table)
    report = BacktestService().run(
        signals,
        BacktestSpecification(
            initial_capital=INITIAL_CAPITAL,
            costs=CostModel(taker_fee_rate=FEE_RATE, slippage_rate=0.0),
        ),
    )

    # 我們的部位是「這一根整根都持有」，成交在前一根收盤；VectorBT 的訊號是
    # 「這一根收盤成交」。所以把部位的轉折往前挪一根，就是同一件事的兩種說法。
    held = signals.positions != 0.0
    previously_held = held.shift(1, fill_value=False)
    portfolio = vbt.Portfolio.from_signals(
        table["close"],
        (held & ~previously_held).shift(-1, fill_value=False),
        (~held & previously_held).shift(-1, fill_value=False),
        init_cash=INITIAL_CAPITAL,
        fees=FEE_RATE,
        slippage=0.0,
        freq="1h",
    )

    their_equity = float(portfolio.value().iloc[-1])
    assert report.trade_count == len(portfolio.trades.records)
    assert report.trade_count > 10
    # f² × 交易筆數的量級：500 根、15 筆交易上實測相對差 1.5e-5
    assert report.final_equity == pytest.approx(their_equity, rel=1e-4)
    # 方向固定：(1 - f) 扣得比 1 / (1 + f) 多，所以我們比較保守
    assert report.final_equity <= their_equity
