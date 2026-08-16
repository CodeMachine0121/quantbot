import numpy as np
import pandas as pd
import pytest

from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)

HOURS_PER_YEAR = 365.0 * 24.0


def make_returns(values: list[float]) -> pd.Series:
    index = pd.date_range("2026-01-01", periods=len(values), freq="1h", tz="UTC")
    return pd.Series(values, index=index, dtype="float64")


def test_the_sharpe_ratio_scales_with_the_square_root_of_the_periods():
    returns = make_returns([0.01, -0.005, 0.008, 0.002, -0.001] * 20)
    service = PerformanceMetricsService()

    hourly = service.sharpe_ratio(returns, periods_per_year=HOURS_PER_YEAR)
    daily = service.sharpe_ratio(returns, periods_per_year=365.0)

    assert hourly is not None
    assert daily is not None
    assert hourly / daily == pytest.approx(float(np.sqrt(24.0)))


def test_a_strategy_that_never_trades_has_no_sharpe_rather_than_zero():
    """一個從不交易的策略的夏普不是 0，是沒有定義。當成 0 會讓它排在賠錢的前面。"""
    flat = make_returns([0.0] * 50)

    assert (
        PerformanceMetricsService().sharpe_ratio(flat, periods_per_year=HOURS_PER_YEAR)
        is None
    )


def test_too_few_observations_have_no_sharpe():
    assert (
        PerformanceMetricsService().sharpe_ratio(
            make_returns([0.01]), periods_per_year=HOURS_PER_YEAR
        )
        is None
    )


def test_missing_values_are_dropped_not_treated_as_zero():
    with_gap = make_returns([0.01, float("nan"), 0.01, -0.02, 0.03])
    without_gap = make_returns([0.01, 0.01, -0.02, 0.03])
    service = PerformanceMetricsService()

    assert service.sharpe_ratio(
        with_gap, periods_per_year=HOURS_PER_YEAR
    ) == pytest.approx(
        service.sharpe_ratio(without_gap, periods_per_year=HOURS_PER_YEAR)
    )


def test_a_losing_strategy_has_a_negative_sharpe():
    losing = make_returns([-0.01, 0.002, -0.008, -0.003, 0.001] * 20)

    sharpe = PerformanceMetricsService().sharpe_ratio(
        losing, periods_per_year=HOURS_PER_YEAR
    )

    assert sharpe is not None
    assert sharpe < 0.0
