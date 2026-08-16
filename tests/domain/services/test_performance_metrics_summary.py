"""Day 22 補上的那幾個指標：回撤、索提諾、勝率與賠率、月報酬。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)
from quantbot.domain.values.cost_model import CostModel

HOURS_PER_YEAR = 365.0 * 24.0


def make_equity(values: list[float]) -> pd.Series:
    index = pd.date_range("2026-01-01", periods=len(values), freq="1h", tz="UTC")
    return pd.Series(values, index=index, dtype="float64")


def make_trades(net_returns: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bars_held": [1] * len(net_returns),
            "net_return": np.asarray(net_returns, dtype="float64"),
        }
    )


def service() -> PerformanceMetricsService:
    return PerformanceMetricsService()


def test_the_maximum_drawdown_is_measured_from_the_running_peak():
    equity = make_equity([100.0, 120.0, 90.0, 110.0])

    assert service().maximum_drawdown(equity) == pytest.approx(-0.25)


def test_the_drawdown_depends_on_the_order_of_the_returns():
    """回撤是一個路徑性質：同一組報酬換個順序就是另一個數字。"""
    rising_first = make_equity([100.0, 110.0, 99.0])
    falling_first = make_equity([100.0, 90.0, 99.0])

    assert service().maximum_drawdown(rising_first) == pytest.approx(-0.1)
    assert service().maximum_drawdown(falling_first) == pytest.approx(-0.1)
    # 深度一樣，但收復的時間不同
    assert service().longest_drawdown_bars(rising_first) == 1
    assert service().longest_drawdown_bars(falling_first) == 2


def test_a_drawdown_that_never_recovers_counts_to_the_end():
    equity = make_equity([100.0, 120.0, 90.0, 80.0, 70.0])

    assert service().longest_drawdown_bars(equity) == 3


def test_sortino_only_punishes_downside_volatility():
    index = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    # 虧損那幾根要有差異，不然它們的標準差是 0，索提諾就沒有定義
    jumpy = pd.Series([0.05, -0.01, 0.06, -0.02, 0.07, -0.015], index=index)

    sharpe = service().sharpe_ratio(jumpy, periods_per_year=HOURS_PER_YEAR)
    sortino = service().sortino_ratio(jumpy, periods_per_year=HOURS_PER_YEAR)

    assert sharpe is not None
    assert sortino is not None
    # 往上跳得很兇不是風險，所以索提諾比夏普高
    assert sortino > sharpe


def test_sortino_is_undefined_without_enough_losing_bars():
    index = pd.date_range("2026-01-01", periods=4, freq="1h", tz="UTC")
    only_up = pd.Series([0.01, 0.02, 0.01, 0.03], index=index)

    assert service().sortino_ratio(only_up, periods_per_year=HOURS_PER_YEAR) is None


def test_the_win_rate_uses_net_returns():
    """一筆賺 0.1% 的交易扣掉 0.3% 來回成本之後是虧的。"""
    trades = make_trades([0.004, -0.002, 0.006, -0.001])

    assert service().win_rate(trades) == pytest.approx(0.5)


def test_a_high_win_rate_with_a_low_payoff_is_a_losing_strategy():
    """60% 勝率配 0.5 的賠率：0.6 × 1 − 0.4 × 2 = −0.2。"""
    trades = make_trades(
        [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, -0.02, -0.02, -0.02, -0.02]
    )

    win_rate = service().win_rate(trades)
    payoff = service().payoff_ratio(trades)

    assert win_rate == pytest.approx(0.6)
    assert payoff == pytest.approx(0.5)
    expected_value = win_rate * payoff - (1.0 - win_rate)
    assert expected_value < 0.0


def test_the_payoff_ratio_is_undefined_when_one_side_is_missing():
    assert service().payoff_ratio(make_trades([0.01, 0.02])) is None
    assert service().payoff_ratio(make_trades([-0.01, -0.02])) is None
    assert service().payoff_ratio(pd.DataFrame(columns=["net_return"])) is None


def test_monthly_returns_compound_rather_than_add():
    index = pd.date_range("2026-01-01", periods=90, freq="1D", tz="UTC")
    equity = pd.Series(
        100.0 * np.power(1.01, np.arange(90, dtype="float64")), index=index
    )

    monthly = service().monthly_returns(equity)

    assert len(monthly) == 3
    # 每一個月的報酬都是「月底除以上個月底」，第一個月從整段的第一個值起算
    assert monthly.iloc[0] == pytest.approx(
        float(equity.resample("ME").last().iloc[0]) / 100.0 - 1.0
    )
    compounded = float((1.0 + monthly).prod())
    assert compounded == pytest.approx(float(equity.iloc[-1]) / 100.0, rel=1e-9)


def test_summarize_carries_the_trial_count_through_untouched():
    equity = make_equity([100.0, 105.0, 102.0])
    report = BacktestReportDto(
        strategy_name="demo",
        bar_count=3,
        trade_count=1,
        trial_count=44,
        initial_capital=100.0,
        costs=CostModel.frictionless(),
        equity=equity,
        gross_equity=equity,
        returns=equity.pct_change().fillna(0.0),
        trades=make_trades([0.02]),
        turnover=1.0,
        cost_paid=0.0,
    )

    summary = service().summarize(report, periods_per_year=HOURS_PER_YEAR)

    assert summary.trial_count == 44
    assert summary.maximum_drawdown == pytest.approx(-3.0 / 105.0)
    assert summary.return_over_maximum_drawdown is not None
