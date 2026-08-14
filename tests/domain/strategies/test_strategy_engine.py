import numpy as np
import pandas as pd
import pytest

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.strategies.constant_condition import Always, Never
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.strategies.threshold_condition import Threshold
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.holding_rules import HoldingRules
from quantbot.domain.values.position_direction import PositionDirection


class Flags(Condition):
    """直接指定每一根成不成立的條件，只在測試裡用。

    它讓引擎的測試不必先湊出一組會產生想要的訊號的特徵值——那樣測到的是特徵，
    不是引擎。
    """

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


def make_table(length: int) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=length, freq="1h", tz="UTC")
    return pd.DataFrame({"close": np.arange(length, dtype="float64")}, index=index)


def strategy_from(
    entry: Condition,
    exit_: Condition,
    *,
    filters: Condition | None = None,
    holding: HoldingRules | None = None,
    direction: PositionDirection = PositionDirection.LONG,
) -> Strategy:
    return Strategy(
        name="test",
        entry=entry,
        exit=exit_,
        filters=filters if filters is not None else Always(),
        holding=holding if holding is not None else HoldingRules.unbounded(),
        direction=direction,
    )


def test_a_signal_on_bar_t_becomes_a_position_on_bar_t_plus_one():
    table = make_table(5)
    strategy = strategy_from(
        Flags("entry", [False, True, False, False, False]),
        Flags("exit", [False, False, False, True, False]),
    )

    positions = StrategyEngine().positions(strategy, table)

    # 第 1 根給訊號 → 第 2 根才持有；第 3 根給出場 → 第 4 根空手
    assert positions.tolist() == [0.0, 0.0, 1.0, 1.0, 0.0]


def test_disabling_the_delay_lets_the_position_start_on_the_signal_bar():
    """signal_delay_bars=0 只用來示範未來函數，Day 19 會拿它算一次帳。"""
    table = make_table(5)
    strategy = strategy_from(
        Flags("entry", [False, True, False, False, False]),
        Flags("exit", [False, False, False, True, False]),
    )

    positions = StrategyEngine(signal_delay_bars=0).positions(strategy, table)

    assert positions.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_a_negative_delay_is_rejected():
    with pytest.raises(ValueError, match="不能是負數"):
        StrategyEngine(signal_delay_bars=-1)


def test_the_position_is_held_until_the_exit_condition_fires():
    table = make_table(6)
    strategy = strategy_from(
        Flags("entry", [True, False, False, False, False, False]),
        Flags("exit", [False, False, False, True, False, False]),
    )

    positions = StrategyEngine().positions(strategy, table)

    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0]


def test_repeated_entry_signals_while_holding_change_nothing():
    table = make_table(5)
    strategy = strategy_from(
        Flags("entry", [True, True, True, True, True]),
        Flags("exit", [False, False, False, False, False]),
    )

    positions = StrategyEngine().positions(strategy, table)

    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0, 1.0]


def test_a_filter_vetoes_the_entry_but_never_closes_a_position():
    table = make_table(5)
    strategy = strategy_from(
        Flags("entry", [True, False, True, False, False]),
        Never(),
        filters=Flags("filter", [False, False, True, False, False]),
    )

    positions = StrategyEngine().positions(strategy, table)

    # 第 0 根的進場被否決；第 2 根放行 → 第 3 根進場。第 3 根過濾又不成立，
    # 但手上的部位不因此離場
    assert positions.tolist() == [0.0, 0.0, 0.0, 1.0, 1.0]


def test_an_exit_on_the_entry_bar_is_ignored_so_every_trade_lasts_a_bar():
    table = make_table(4)
    strategy = strategy_from(
        Flags("entry", [True, False, False, False]),
        Flags("exit", [True, False, True, False]),
    )

    positions = StrategyEngine().positions(strategy, table)

    # 位移之後兩個訊號都落在第 1 根，進場勝出；出場等到第 3 根
    assert positions.tolist() == [0.0, 1.0, 1.0, 0.0]


def test_a_position_still_open_at_the_end_is_counted():
    table = make_table(4)
    strategy = strategy_from(Flags("entry", [True, False, False, False]), Never())

    positions = StrategyEngine().positions(strategy, table)

    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0]


def test_maximum_holding_bars_closes_a_position_that_never_got_an_exit():
    table = make_table(7)
    strategy = strategy_from(
        Flags("entry", [True, False, False, False, False, False, False]),
        Never(),
        holding=HoldingRules(maximum_holding_bars=3),
    )

    positions = StrategyEngine().positions(strategy, table)

    # 第 1 根進場，抱滿 3 根（1、2、3），第 4 根離場
    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]


def test_cooldown_blocks_re_entry_for_the_given_number_of_bars():
    table = make_table(8)
    strategy = strategy_from(
        Flags("entry", [True, True, True, True, True, True, True, True]),
        Never(),
        holding=HoldingRules(maximum_holding_bars=2, cooldown_bars=2),
    )

    positions = StrategyEngine().positions(strategy, table)

    # 1–2 持有，3–4 冷卻，5–6 持有，7 冷卻
    assert positions.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0]


def test_the_warmup_of_the_condition_tree_blocks_the_first_bars():
    table = make_table(4)

    class LateEntry(Condition):
        @property
        def name(self) -> str:
            return "late"

        @property
        def required_features(self) -> frozenset[str]:
            return frozenset()

        @property
        def warmup_bar_count(self) -> int:
            return 2

        def _evaluate(self, table: pd.DataFrame) -> pd.Series:
            return pd.Series(True, index=table.index)

    positions = StrategyEngine().positions(strategy_from(LateEntry(), Never()), table)

    # 暖機 2 根加上位移 1 根，所以最快在第 3 根持有
    assert positions.tolist() == [0.0, 0.0, 0.0, 1.0]


def test_buy_and_hold_holds_from_the_second_bar_onwards():
    table = make_table(4)

    positions = StrategyEngine().positions(Strategy.buy_and_hold(), table)

    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0]


def test_a_short_strategy_produces_negative_weights():
    table = make_table(3)
    strategy = strategy_from(
        Flags("entry", [True, False, False]),
        Never(),
        direction=PositionDirection.SHORT,
    )

    positions = StrategyEngine().positions(strategy, table)

    assert positions.tolist() == [0.0, -1.0, -1.0]


def test_positions_keep_the_index_and_are_float64():
    table = make_table(3)
    strategy = strategy_from(Threshold("close", Comparison.ABOVE, 0.5), Never())

    positions = StrategyEngine().positions(strategy, table)

    assert positions.index.equals(table.index)
    assert positions.dtype == "float64"
    assert positions.name == "position_test"


def test_an_empty_table_produces_an_empty_position_series():
    table = make_table(0)

    positions = StrategyEngine().positions(Strategy.buy_and_hold(), table)

    assert positions.empty
