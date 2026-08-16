import numpy as np
import pandas as pd
import pytest

from quantbot.domain.dto.performance_summary import PerformanceSummaryDto
from quantbot.domain.dto.strategy_comparison_report import StrategyComparisonReportDto
from quantbot.domain.services.strategy_correlation_service import (
    StrategyCorrelationService,
)


def make_returns(values: list[float]) -> pd.Series:
    index = pd.date_range("2026-01-01", periods=len(values), freq="1h", tz="UTC")
    return pd.Series(values, index=index, dtype="float64")


def summary(name: str, *, bar_count: int = 10, total_return: float = 0.0):
    return PerformanceSummaryDto(
        strategy_name=name,
        trial_count=1,
        bar_count=bar_count,
        trade_count=3,
        exposure=0.5,
        total_return=total_return,
        maximum_drawdown=-0.1,
        longest_drawdown_bars=4,
        sharpe_ratio=0.5,
        sortino_ratio=0.6,
        win_rate=0.5,
        payoff_ratio=1.2,
    )


def test_identical_strategies_are_perfectly_correlated():
    values = make_returns([0.01, -0.02, 0.03, -0.01, 0.02])

    assert StrategyCorrelationService().pairwise(values, values) == pytest.approx(1.0)


def test_opposite_strategies_are_perfectly_negatively_correlated():
    values = make_returns([0.01, -0.02, 0.03, -0.01, 0.02])

    assert StrategyCorrelationService().pairwise(values, -values) == pytest.approx(-1.0)


def test_bars_where_both_are_flat_are_excluded():
    """兩個曝險都很低的策略，一堆 0 會把相關係數往 0 拉。"""
    first = make_returns([0.0] * 20 + [0.01, -0.02, 0.03, -0.01])
    second = make_returns([0.0] * 20 + [0.01, -0.02, 0.03, -0.01])

    with_zeros = float(first.corr(second))
    without_zeros = StrategyCorrelationService().pairwise(first, second)

    assert without_zeros == pytest.approx(1.0)
    assert with_zeros == pytest.approx(1.0)  # 完全同步時兩種算法一樣

    # 換成「同時進場但方向相反」：排除空手的根之後才看得出來
    opposite = make_returns([0.0] * 20 + [-0.01, 0.02, -0.03, 0.01])
    assert StrategyCorrelationService().pairwise(first, opposite) == pytest.approx(-1.0)


def test_too_little_overlap_is_undefined_rather_than_zero():
    first = make_returns([0.01, 0.0, 0.0, 0.0])
    second = make_returns([0.0, 0.0, 0.0, 0.02])

    value = StrategyCorrelationService().pairwise(first, second)

    assert np.isnan(value)


def test_the_matrix_is_symmetric_with_ones_on_the_diagonal():
    values = {
        "a": make_returns([0.01, -0.02, 0.03, -0.01, 0.02]),
        "b": make_returns([0.02, -0.01, 0.01, -0.02, 0.03]),
        "c": make_returns([-0.01, 0.02, -0.03, 0.01, -0.02]),
    }

    matrix = StrategyCorrelationService().matrix(values)

    assert list(matrix.index) == ["a", "b", "c"]
    for name in values:
        assert matrix.loc[name, name] == pytest.approx(1.0)
    assert matrix.loc["a", "c"] == pytest.approx(matrix.loc["c", "a"])
    assert matrix.loc["a", "c"] == pytest.approx(-1.0)


def test_one_strategy_cannot_be_correlated_with_anything():
    with pytest.raises(ValueError, match="至少要兩個策略"):
        StrategyCorrelationService().matrix({"only": make_returns([0.01, 0.02])})


def test_a_comparison_across_different_data_lengths_is_rejected():
    """公平比較的第一個條件：同一段資料。這條由型別保證，不靠使用者記得。"""
    matrix = pd.DataFrame(
        [[1.0, 0.2], [0.2, 1.0]], index=["a", "b"], columns=["a", "b"]
    )

    with pytest.raises(ValueError, match="同一段資料"):
        StrategyComparisonReportDto(
            period_label="test",
            baseline=summary("baseline", bar_count=10),
            summaries=(summary("a", bar_count=10), summary("b", bar_count=9)),
            correlation=matrix,
        )


def test_the_comparison_ranks_by_sharpe_and_finds_the_most_correlated_pair():
    matrix = pd.DataFrame(
        [[1.0, 0.81], [0.81, 1.0]], index=["a", "b"], columns=["a", "b"]
    )
    report = StrategyComparisonReportDto(
        period_label="test",
        baseline=summary("baseline", total_return=-0.35),
        summaries=(
            summary("a", total_return=-0.02),
            summary("b", total_return=-0.60),
        ),
        correlation=matrix,
    )

    assert [item.strategy_name for item in report.ranked_by_sharpe()] == ["a", "b"]
    assert [item.strategy_name for item in report.beating_the_baseline()] == ["a"]
    assert report.most_correlated_pair == ("a", "b", pytest.approx(0.81))


def test_excess_return_is_measured_against_the_baseline():
    baseline = summary("baseline", total_return=-0.35)
    strategy = summary("a", total_return=-0.02)

    assert strategy.excess_over(baseline) == pytest.approx(0.33)
