import numpy as np
import pandas as pd
import pytest

from quantbot.domain.strategies.condition import AllOf, AnyOf, Not
from quantbot.domain.strategies.constant_condition import Always, Never
from quantbot.domain.strategies.crossover_condition import Crossover
from quantbot.domain.strategies.event_condition import Event
from quantbot.domain.strategies.feature_comparison_condition import FeatureComparison
from quantbot.domain.strategies.range_condition import Range
from quantbot.domain.strategies.threshold_condition import Threshold
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.cross_direction import CrossDirection

NAN = float("nan")


def make_table(**columns: list[float]) -> pd.DataFrame:
    length = len(next(iter(columns.values())))
    index = pd.date_range("2026-01-01", periods=length, freq="1h", tz="UTC")
    return pd.DataFrame(
        {name: np.asarray(values, dtype="float64") for name, values in columns.items()},
        index=index,
    )


def test_threshold_compares_against_a_constant():
    table = make_table(rsi_14=[10.0, 70.0, 80.0])

    above = Threshold("rsi_14", Comparison.ABOVE, 70.0).evaluate(table)
    at_least = Threshold("rsi_14", Comparison.AT_LEAST, 70.0).evaluate(table)

    assert above.tolist() == [False, False, True]
    # 剛好等於 70 的那一根，含不含等於答案相反
    assert at_least.tolist() == [False, True, True]


def test_threshold_treats_missing_values_as_not_satisfied():
    table = make_table(rsi_14=[NAN, 80.0])

    satisfied = Threshold("rsi_14", Comparison.ABOVE, 70.0).evaluate(table)

    assert satisfied.tolist() == [False, True]


def test_negation_turns_missing_values_into_satisfied():
    """取反之後，暖機期的 NaN 會變成成立——這是 Not 的那個安靜陷阱。"""
    table = make_table(rsi_14=[NAN, 80.0, 10.0])

    satisfied = (~Threshold("rsi_14", Comparison.ABOVE, 70.0)).evaluate(table)

    assert satisfied.tolist() == [True, False, True]


def test_crossover_only_fires_on_the_turning_bar():
    table = make_table(
        ema_12=[1.0, 1.0, 3.0, 4.0, 1.0],
        ema_26=[2.0, 2.0, 2.0, 2.0, 2.0],
    )

    up = Crossover("ema_12", CrossDirection.UP, "ema_26").evaluate(table)
    down = Crossover("ema_12", CrossDirection.DOWN, "ema_26").evaluate(table)

    # 第 2 根翻上去、第 4 根翻下來；站在上面的第 3 根不算一次交叉
    assert up.tolist() == [False, False, True, False, False]
    assert down.tolist() == [False, False, False, False, True]


def test_crossover_does_not_fire_when_the_previous_bar_was_warming_up():
    table = make_table(ema_12=[NAN, 3.0, 3.0], ema_26=[NAN, 2.0, 2.0])

    fired = Crossover("ema_12", CrossDirection.UP, "ema_26").evaluate(table)

    assert fired.tolist() == [False, False, False]


def test_feature_comparison_reads_two_columns():
    table = make_table(close=[100.0, 90.0], vwap_session=[95.0, 95.0])

    condition = FeatureComparison("close", Comparison.ABOVE, "vwap_session")

    assert condition.evaluate(table).tolist() == [True, False]
    assert condition.required_features == frozenset({"close", "vwap_session"})


def test_range_includes_both_ends_and_rejects_an_inverted_interval():
    table = make_table(rsi_14=[30.0, 50.0, 70.0, 90.0])

    inside = Range("rsi_14", 30.0, 70.0).evaluate(table)

    assert inside.tolist() == [True, True, True, False]
    with pytest.raises(ValueError, match="下界不能大於上界"):
        Range("rsi_14", 70.0, 30.0)


def test_event_needs_both_non_zero_and_non_missing():
    table = make_table(breakout_high_20=[NAN, 0.0, 1.0])

    fired = Event("breakout_high_20").evaluate(table)

    assert fired.tolist() == [False, False, True]


def test_operators_build_a_tree_and_flatten_the_same_operator():
    first = Threshold("a", Comparison.ABOVE, 1.0)
    second = Threshold("b", Comparison.ABOVE, 2.0)
    third = Threshold("c", Comparison.ABOVE, 3.0)

    combined = first & second & third

    assert isinstance(combined, AllOf)
    # (a & b) & c 攤平成三元，所以 describe() 不受括號寫法影響
    assert len(combined.conditions) == 3
    assert combined.required_features == frozenset({"a", "b", "c"})
    assert combined.describe() == "(a > 1 AND b > 2 AND c > 3)"


def test_or_and_not_compose_into_conditions_as_well():
    first = Threshold("a", Comparison.ABOVE, 1.0)
    second = Threshold("b", Comparison.BELOW, 2.0)

    combined = ~(first | second)

    assert isinstance(combined, Not)
    assert isinstance(combined.condition, AnyOf)
    assert combined.describe() == "NOT (a > 1 OR b < 2)"


def test_combined_conditions_evaluate_element_wise():
    table = make_table(a=[2.0, 2.0, 0.0], b=[1.0, 3.0, 3.0])

    both = (
        Threshold("a", Comparison.ABOVE, 1.0) & Threshold("b", Comparison.ABOVE, 2.0)
    ).evaluate(table)
    either = (
        Threshold("a", Comparison.ABOVE, 1.0) | Threshold("b", Comparison.ABOVE, 2.0)
    ).evaluate(table)

    assert both.tolist() == [False, True, False]
    assert either.tolist() == [True, True, True]


def test_warmup_is_the_longest_in_the_tree():
    crossing = Crossover("ema_12", CrossDirection.UP, "ema_26")
    threshold = Threshold("rsi_14", Comparison.BELOW, 70.0)

    assert threshold.warmup_bar_count == 0
    assert crossing.warmup_bar_count == 1
    assert (threshold & crossing).warmup_bar_count == 1


def test_a_missing_column_is_reported_with_the_available_ones():
    table = make_table(ema_12=[1.0])

    with pytest.raises(KeyError, match="ema_26"):
        Crossover("ema_12", CrossDirection.UP, "ema_26").evaluate(table)


def test_constant_conditions_need_nothing_and_keep_the_index():
    table = make_table(anything=[1.0, 2.0])

    assert Always().required_features == frozenset()
    assert Always().evaluate(table).tolist() == [True, True]
    assert Never().evaluate(table).tolist() == [False, False]


def test_empty_composites_are_rejected_at_construction():
    with pytest.raises(ValueError, match="至少要有一個條件"):
        AllOf()
    with pytest.raises(ValueError, match="至少要有一個條件"):
        AnyOf()


def test_evaluated_series_is_boolean_named_and_index_aligned():
    table = make_table(rsi_14=[10.0, 80.0])

    evaluated = Threshold("rsi_14", Comparison.ABOVE, 70.0).evaluate(table)

    assert evaluated.dtype == bool
    assert evaluated.name == "rsi_14_above_70"
    assert evaluated.index.equals(table.index)
