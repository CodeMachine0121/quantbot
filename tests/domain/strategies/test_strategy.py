import pytest

from quantbot.domain.strategies.constant_condition import Always, Never
from quantbot.domain.strategies.crossover_condition import Crossover
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.threshold_condition import Threshold
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.cross_direction import CrossDirection
from quantbot.domain.values.holding_rules import HoldingRules


def make_strategy() -> Strategy:
    return Strategy(
        name="trend_ema_rsi",
        entry=Crossover("ema_12", CrossDirection.UP, "ema_26"),
        exit=Crossover("ema_12", CrossDirection.DOWN, "ema_26"),
        filters=Threshold("rsi_14", Comparison.BELOW, 70.0),
    )


def test_required_features_is_derived_from_all_three_trees():
    strategy = make_strategy()

    assert strategy.required_features == frozenset({"ema_12", "ema_26", "rsi_14"})


def test_warmup_is_the_longest_of_the_three_trees():
    assert make_strategy().warmup_bar_count == 1


def test_a_strategy_without_a_filter_lets_every_entry_through():
    strategy = Strategy(name="bare", entry=Always(), exit=Never())

    assert isinstance(strategy.filters, Always)
    assert strategy.holding == HoldingRules.unbounded()


def test_buy_and_hold_is_an_ordinary_strategy_not_an_engine_special_case():
    baseline = Strategy.buy_and_hold()

    assert isinstance(baseline.entry, Always)
    assert isinstance(baseline.exit, Never)
    assert baseline.required_features == frozenset()
    assert baseline.warmup_bar_count == 0


def test_describe_prints_every_tree_and_the_derived_features():
    described = make_strategy().describe()

    assert "ema_12 ↑ cross ema_26" in described
    assert "rsi_14 < 70" in described
    assert "無時間限制" in described
    assert "['ema_12', 'ema_26', 'rsi_14']" in described


@pytest.mark.parametrize(
    ("maximum", "cooldown"),
    [(0, None), (None, 0), (-1, None)],
)
def test_non_positive_holding_rules_are_rejected(maximum, cooldown):
    with pytest.raises(ValueError, match="必須 >= 1"):
        HoldingRules(maximum_holding_bars=maximum, cooldown_bars=cooldown)


def test_holding_rules_describe_both_limits():
    rules = HoldingRules(maximum_holding_bars=48, cooldown_bars=12)

    assert rules.describe() == "最多抱 48 根、出場後冷卻 12 根"
