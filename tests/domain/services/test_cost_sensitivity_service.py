import numpy as np
import pandas as pd
import pytest

from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.cost_sensitivity_service import CostSensitivityService
from quantbot.domain.strategies.condition import Condition
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.strategy_signals import StrategySignals


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


def service() -> CostSensitivityService:
    return CostSensitivityService(backtest=BacktestService())


def churning_signals(bar_count: int = 400) -> StrategySignals:
    """一個交易很頻繁、毛利明顯為正的策略。它對成本最敏感。

    走勢與訊號都是寫死的，不用亂數：這個測試要問的是「費率變高報酬會怎麼變」，
    而那個問題需要一個毛利確定為正的起點。亂數走勢有時候是負的，那時候
    「由賺轉賠的位置」根本不存在，測試就變成有時候通過。
    """
    prices = 100.0 * np.power(1.005, np.arange(bar_count, dtype="float64"))
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    table = pd.DataFrame({"close": prices}, index=index)
    positions = np.arange(bar_count)
    strategy = Strategy(
        name="churn",
        entry=Flags("entry", list(positions % 4 == 0)),
        exit=Flags("exit", list(positions % 4 == 2)),
    )
    return StrategyEngine().signals(strategy, table)


def test_higher_fees_never_produce_a_higher_return():
    signals = churning_signals()

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.0, 0.0005, 0.001, 0.002, 0.005],
        slippage_rate=0.0,
    )

    returns = [row.total_return for row in report.rows]
    assert returns == sorted(returns, reverse=True)
    # 費率為 0 的那一列就是毛報酬
    assert report.rows[0].total_return == pytest.approx(report.gross_total_return)


def test_the_rows_come_back_sorted_by_fee_rate_whatever_order_they_went_in():
    signals = churning_signals()

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.001, 0.0002, 0.0005],
        slippage_rate=0.0,
    )

    assert [row.taker_fee_rate for row in report.rows] == [0.0002, 0.0005, 0.001]


def test_the_break_even_rate_is_interpolated_between_two_grid_points():
    signals = churning_signals()

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.0, 0.001, 0.002, 0.005, 0.01, 0.02],
        slippage_rate=0.0,
    )

    assert report.break_even_round_trip_rate is not None
    # 內插出來的值必須落在網格的兩端之間，而且不等於任何一個網格點
    assert 0.0 < report.break_even_round_trip_rate < 0.04
    assert report.break_even_round_trip_rate not in {
        row.round_trip_rate for row in report.rows
    }


def test_a_strategy_that_already_loses_without_costs_has_no_break_even_point():
    generator = np.random.default_rng(3)
    bar_count = 300
    prices = 100.0 * np.exp(np.cumsum(generator.normal(-0.002, 0.01, bar_count)))
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    table = pd.DataFrame({"close": prices}, index=index)
    strategy = Strategy(
        name="losing",
        entry=Flags("entry", [True] * bar_count),
        exit=Flags("exit", [False] * bar_count),
    )
    signals = StrategyEngine().signals(strategy, table)

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.0, 0.001],
        slippage_rate=0.0,
    )

    assert report.gross_total_return < 0.0
    assert report.break_even_round_trip_rate is None


def test_a_strategy_still_profitable_at_the_highest_fee_reports_no_break_even():
    """回一個網格端點會被誤讀成「剛好在這裡由賺轉賠」，所以回 None。"""
    index = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
    table = pd.DataFrame({"close": [100.0, 110.0, 121.0, 133.1, 146.41]}, index=index)
    strategy = Strategy(
        name="winning",
        entry=Flags("entry", [True, False, False, False, False]),
        exit=Flags("exit", [False] * 5),
    )
    signals = StrategyEngine().signals(strategy, table)

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.0001, 0.001],
        slippage_rate=0.0,
    )

    assert report.rows[-1].total_return > 0.0
    assert report.break_even_round_trip_rate is None


def test_turnover_per_trade_is_about_two_for_a_normal_strategy():
    signals = churning_signals()

    report = service().scan(
        signals,
        initial_capital=10_000.0,
        taker_fee_rates=[0.001],
        slippage_rate=0.0,
    )

    assert report.cost_per_trade_rate == pytest.approx(2.0, abs=0.05)


def test_an_empty_fee_grid_is_rejected():
    with pytest.raises(ValueError, match="至少要有一個費率"):
        service().scan(
            churning_signals(),
            initial_capital=10_000.0,
            taker_fee_rates=[],
            slippage_rate=0.0,
        )
