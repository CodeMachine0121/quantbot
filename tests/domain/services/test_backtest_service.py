import numpy as np
import pandas as pd
import pytest

from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.strategies.condition import Condition
from quantbot.domain.strategies.constant_condition import Never
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.cost_model import CostModel
from quantbot.domain.values.strategy_signals import StrategySignals
from tests.reference.reference_backtest import ReferenceBacktest


class Flags(Condition):
    """直接指定每一根成不成立，只在測試裡用。"""

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


def make_table(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(prices), freq="1h", tz="UTC")
    return pd.DataFrame({"close": np.asarray(prices, dtype="float64")}, index=index)


def signals_for(
    table: pd.DataFrame, entry: list[bool], exit_: list[bool] | None = None
) -> StrategySignals:
    strategy = Strategy(
        name="test",
        entry=Flags("entry", entry),
        exit=Flags("exit", exit_) if exit_ is not None else Never(),
    )
    return StrategyEngine().signals(strategy, table)


def test_holding_through_a_rise_earns_that_rise():
    table = make_table([100.0, 100.0, 110.0, 121.0])
    signals = signals_for(table, [True, False, False, False])

    report = BacktestService().run(signals, BacktestSpecification.ideal(1_000.0))

    # 第 1 根起持有，賺到第 2、3 根的兩次 10%
    assert report.total_return == pytest.approx(0.21)
    assert report.final_equity == pytest.approx(1_210.0)


def test_being_flat_earns_nothing_not_even_the_market():
    table = make_table([100.0, 110.0, 121.0])
    signals = signals_for(table, [False, False, False])

    report = BacktestService().run(signals, BacktestSpecification.ideal())

    assert report.total_return == pytest.approx(0.0)
    assert report.trade_count == 0
    assert report.trades.empty


def test_costs_are_charged_on_turnover_twice_per_round_trip():
    table = make_table([100.0, 100.0, 100.0, 100.0])
    signals = signals_for(
        table, [True, False, False, False], [False, True, False, False]
    )
    costs = CostModel(taker_fee_rate=0.001, slippage_rate=0.0)

    report = BacktestService().run(
        signals, BacktestSpecification(initial_capital=1_000.0, costs=costs)
    )

    # 價格完全沒動，所以虧的就是進出各一次的手續費（複利之後略小於兩倍）
    assert report.total_return == pytest.approx(0.999 * 0.999 - 1.0, abs=1e-12)
    assert report.turnover == pytest.approx(2.0)
    assert report.gross_total_return == pytest.approx(0.0)


def test_holding_continuously_pays_no_cost_between_bars():
    table = make_table([100.0] * 10)
    signals = signals_for(table, [True] + [False] * 9)

    report = BacktestService().run(
        signals,
        BacktestSpecification(initial_capital=1_000.0, costs=CostModel()),
    )

    # 只有一次進場，而且沒有出場（結束時還開著），所以只付一邊
    assert report.turnover == pytest.approx(1.0)


def test_the_entry_price_is_the_previous_bar_close():
    table = make_table([100.0, 200.0, 400.0, 400.0])
    signals = signals_for(
        table, [True, False, False, False], [False, False, True, False]
    )

    trades = BacktestService().run(signals, BacktestSpecification.ideal()).trades

    assert len(trades) == 1
    # 進場訊號在第 0 根 → 第 1 根持有 → 成交價是第 0 根的收盤價 100。
    # 出場訊號在第 2 根，同樣位移一根 → 第 3 根才空手，所以賣在第 2 根的收盤價 400
    assert trades["entry_price"].iloc[0] == pytest.approx(100.0)
    assert trades["exit_price"].iloc[0] == pytest.approx(400.0)
    assert trades["bars_held"].iloc[0] == 2


def test_a_position_open_at_the_end_still_becomes_a_trade():
    table = make_table([100.0, 100.0, 150.0])
    signals = signals_for(table, [True, False, False])

    trades = BacktestService().run(signals, BacktestSpecification.ideal()).trades

    assert len(trades) == 1
    assert trades["exit_price"].iloc[0] == pytest.approx(150.0)
    assert trades["gross_return"].iloc[0] == pytest.approx(0.5)


def test_the_vectorized_equity_matches_the_bar_by_bar_reference():
    """向量化與逐根模擬（Backtrader 那一類的做法）必須逐根相同。"""
    generator = np.random.default_rng(1019)
    prices = 100.0 * np.exp(np.cumsum(generator.normal(0.0, 0.01, 500)))
    table = make_table(list(prices))
    entry = list(generator.uniform(size=500) < 0.05)
    exit_ = list(generator.uniform(size=500) < 0.05)
    signals = signals_for(table, entry, exit_)
    costs = CostModel(taker_fee_rate=0.001, slippage_rate=0.0005)

    report = BacktestService().run(
        signals, BacktestSpecification(initial_capital=10_000.0, costs=costs)
    )
    reference = ReferenceBacktest(
        initial_capital=10_000.0, one_way_rate=costs.one_way_rate
    ).equity(signals.positions, table["close"])

    assert report.trade_count > 5
    np.testing.assert_allclose(
        report.equity.to_numpy(), reference.to_numpy(), rtol=1e-12
    )


def test_gross_and_net_only_differ_by_the_cost_model():
    generator = np.random.default_rng(7)
    prices = 100.0 * np.exp(np.cumsum(generator.normal(0.0, 0.01, 200)))
    table = make_table(list(prices))
    signals = signals_for(
        table,
        list(generator.uniform(size=200) < 0.1),
        list(generator.uniform(size=200) < 0.1),
    )

    ideal = BacktestService().run(signals, BacktestSpecification.ideal())
    charged = BacktestService().run(signals, BacktestSpecification())

    assert ideal.total_return == pytest.approx(ideal.gross_total_return)
    assert charged.gross_total_return == pytest.approx(ideal.gross_total_return)
    assert charged.total_return < charged.gross_total_return


def test_a_report_cannot_be_built_without_a_trial_count():
    """任何呈現的回測結果都要標注試了幾個組合，所以那個欄位沒有預設值。"""
    table = make_table([100.0, 101.0])
    signals = signals_for(table, [True, False])

    report = BacktestService().run(signals, BacktestSpecification.ideal())

    assert report.trial_count == 1
    with pytest.raises(ValueError, match="trial_count"):
        BacktestService().run(signals, BacktestSpecification.ideal(), trial_count=0)


def test_the_cost_share_of_gross_profit_is_none_when_there_is_no_profit():
    table = make_table([100.0, 100.0, 90.0])
    signals = signals_for(table, [True, False, False])

    report = BacktestService().run(signals, BacktestSpecification())

    assert report.gross_total_return < 0.0
    assert report.cost_share_of_gross_profit is None


def test_an_empty_table_produces_an_empty_report():
    table = make_table([])
    signals = signals_for(table, [])

    report = BacktestService().run(signals, BacktestSpecification.ideal())

    assert report.bar_count == 0
    assert report.total_return == pytest.approx(0.0)
    assert report.trades.empty
