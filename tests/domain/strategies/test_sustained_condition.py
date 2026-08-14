import numpy as np
import pandas as pd
import pytest

from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.crossover_condition import Crossover
from quantbot.domain.strategies.sustained_condition import Sustained
from quantbot.domain.strategies.threshold_condition import Threshold
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.cross_direction import CrossDirection

NAN = float("nan")


def make_table(**columns: list[float]) -> pd.DataFrame:
    length = len(next(iter(columns.values())))
    index = pd.date_range("2026-01-01", periods=length, freq="1h", tz="UTC")
    return pd.DataFrame(
        {name: np.asarray(values, dtype="float64") for name, values in columns.items()},
        index=index,
    )


def deep_enough() -> Threshold:
    return Threshold("deviation", Comparison.AT_MOST, -2.0)


def test_only_the_bars_where_the_streak_is_complete_are_satisfied():
    table = make_table(deviation=[-3.0, -1.0, -3.0, -3.0, -3.0, -1.0])

    satisfied = Sustained(deep_enough(), 2).evaluate(table)

    # 第 0 根單獨成立但湊不滿兩根；第 3、4 根各是一段連續兩根的第二根
    assert satisfied.tolist() == [False, False, False, True, True, False]


def test_a_single_bar_spike_does_not_satisfy_a_two_bar_streak():
    """一根長下影線就足以觸發單根門檻，這是均值回歸要它的理由。"""
    table = make_table(deviation=[-0.5, -4.0, -0.5])

    single = deep_enough().evaluate(table)
    sustained = Sustained(deep_enough(), 2).evaluate(table)

    assert single.tolist() == [False, True, False]
    assert sustained.tolist() == [False, False, False]


def test_the_warmup_prefix_is_not_satisfied():
    table = make_table(deviation=[-3.0, -3.0, -3.0])

    satisfied = Sustained(deep_enough(), 3).evaluate(table)

    # 前兩根湊不滿三根，而 rolling 的 NaN 比對之後就是 False
    assert satisfied.tolist() == [False, False, True]


def test_missing_values_break_a_streak():
    table = make_table(deviation=[-3.0, NAN, -3.0, -3.0])

    satisfied = Sustained(deep_enough(), 2).evaluate(table)

    assert satisfied.tolist() == [False, False, False, True]


def test_warmup_adds_up_along_the_chain():
    crossing = Crossover("ema_12", CrossDirection.UP, "ema_26")

    assert Sustained(crossing, 3).warmup_bar_count == 1 + 3 - 1
    assert Sustained(deep_enough(), 4).warmup_bar_count == 0 + 4 - 1


def test_it_composes_with_the_operators_like_any_other_condition():
    table = make_table(
        deviation=[-3.0, -3.0, -3.0],
        activity=[1.0, -1.0, 1.0],
    )

    combined = Sustained(deep_enough(), 2) & Threshold(
        "activity", Comparison.AT_LEAST, 0.0
    )

    assert combined.evaluate(table).tolist() == [False, False, True]
    assert combined.required_features == frozenset({"deviation", "activity"})


def test_one_bar_is_rejected_because_it_would_mean_nothing():
    with pytest.raises(ValueError, match="必須 >= 2"):
        Sustained(deep_enough(), 1)


def test_the_registry_builds_it_with_a_child_and_a_parameter():
    specification = ConditionSpecification(
        kind="sustained",
        parameters={"bars": 2},
        children=(
            ConditionSpecification(
                kind="threshold",
                parameters={
                    "feature": "vwap_session_deviation",
                    "comparison": "at_most",
                    "value": -2.0,
                },
            ),
        ),
    )

    built = ConditionRegistry().build(specification)

    assert isinstance(built, Sustained)
    assert built.describe() == "vwap_session_deviation <= -2 連續 2 根"


def test_the_registry_rejects_more_than_one_child():
    specification = ConditionSpecification(
        kind="sustained",
        parameters={"bars": 2},
        children=(
            ConditionSpecification(kind="always"),
            ConditionSpecification(kind="never"),
        ),
    )

    with pytest.raises(ValueError, match="只能有一個子節點"):
        ConditionRegistry().build(specification)
