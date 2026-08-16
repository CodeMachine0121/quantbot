"""內附的三份策略設定：載得起來、組得出來、而且真的表達了不同的交易哲學。

跑不起來的設定檔比沒有設定檔糟，所以它們是測試的對象而不只是範例。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.infrastructure.configuration.yaml_strategy_specification_loader import (
    YamlStrategySpecificationLoader,
)

STRATEGIES = (
    Path(__file__).resolve().parents[3]
    / "quantbot"
    / "infrastructure"
    / "configuration"
    / "strategies"
)
SHIPPED = ("trend_ema_rsi", "mean_reversion_vwap", "momentum_breakout")


def load(name: str) -> StrategySpecification:
    return YamlStrategySpecificationLoader().load(STRATEGIES / f"{name}.yaml")


def assembly() -> StrategyAssemblyService:
    return StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )


def make_table(bar_count: int = 600, seed: int = 18) -> pd.DataFrame:
    """一張欄位齊全的假表，只為了確認條件樹接得上、算得動。

    數值本身沒有意義（真實資料上的行為靠 signals_command 實跑），這裡要的是
    「三份設定引用的每一欄都存在，而且引擎跑得完」。
    """
    generator = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    close = 100.0 * np.exp(np.cumsum(generator.normal(0.0, 0.01, bar_count)))
    return pd.DataFrame(
        {
            "close": close,
            "ema_12": pd.Series(close, index=index).ewm(span=12).mean(),
            "ema_26": pd.Series(close, index=index).ewm(span=26).mean(),
            "rsi_14": generator.uniform(20.0, 90.0, bar_count),
            "vwap_session_deviation": generator.normal(0.0, 1.5, bar_count),
            "activity_trade_count_rolling_168": generator.normal(0.0, 1.2, bar_count),
            "activity_absolute_return_rolling_168": generator.normal(
                0.0, 1.2, bar_count
            ),
            "breakout_high_20": (generator.uniform(size=bar_count) < 0.1).astype(
                "float64"
            ),
        },
        index=index,
    )


@pytest.mark.parametrize("name", SHIPPED)
def test_every_shipped_configuration_loads_and_assembles(name):
    strategy = assembly().assemble(load(name))

    assert strategy.name == name
    assert strategy.required_features


@pytest.mark.parametrize("name", SHIPPED)
def test_every_shipped_configuration_produces_positions(name):
    table = make_table()

    signals = StrategyEngine().signals(assembly().assemble(load(name)), table)

    assert signals.bar_count == len(table)
    assert signals.trade_count > 0


def test_the_two_new_strategies_declare_their_time_rules():
    """時間規則不是裝飾：均值回歸沒有它就會抱著一個永遠不回歸的部位到資料結束。"""
    reversion = assembly().assemble(load("mean_reversion_vwap"))
    momentum = assembly().assemble(load("momentum_breakout"))

    assert reversion.holding.maximum_holding_bars == 48
    assert reversion.holding.cooldown_bars == 12
    assert momentum.holding.maximum_holding_bars == 24
    assert momentum.holding.cooldown_bars == 6


def test_the_three_strategies_do_not_share_a_single_feature():
    """同一組積木表達三種哲學的證據之一：它們讀的欄位幾乎不重疊。"""
    required = [assembly().assemble(load(name)).required_features for name in SHIPPED]

    assert required[0] & required[1] == frozenset()
    assert required[0] & required[2] == frozenset()


def never_reverting_table(bar_count: int = 200) -> pd.DataFrame:
    """一段「跌破門檻之後再也沒回到均價」的走勢。

    這是均值回歸最怕的情況，而它剛好也是唯一能證明最大持有根數在動作的資料：
    出場條件永遠不成立，所以離場只可能來自時間規則。
    """
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    deviation = np.full(bar_count, -3.0)
    return pd.DataFrame(
        {
            "vwap_session_deviation": deviation,
            "activity_trade_count_rolling_168": np.zeros(bar_count),
        },
        index=index,
    )


def test_the_time_rules_close_a_position_that_the_exit_condition_never_would():
    """出場條件永遠不成立時，離場只能來自時間規則。"""
    from dataclasses import replace

    from quantbot.domain.values.holding_rules import HoldingRules

    table = never_reverting_table()
    specification = load("mean_reversion_vwap")
    engine = StrategyEngine()

    bounded = engine.signals(assembly().assemble(specification), table)
    unbounded = engine.signals(
        assembly().assemble(replace(specification, holding=HoldingRules.unbounded())),
        table,
    )

    # 沒有時間規則就一路抱到資料結束，只有一筆交易
    assert unbounded.trade_count == 1
    assert unbounded.exposure > 0.97
    # 有了 48 根上限與 12 根冷卻，同一段資料變成好幾筆，曝險降到八成
    assert bounded.trade_count > 1
    assert bounded.exposure < 0.85
    assert bounded.exposure == pytest.approx(48 / 60, abs=0.05)


def test_crossing_two_configurations_takes_entry_from_one_and_exit_from_the_other():
    """積木化真正要換到的東西：換掉一半而不必改任何 Python。"""
    trend = load("trend_ema_rsi")
    momentum = load("momentum_breakout")

    crossed = trend.with_exit_from(momentum)
    strategy = assembly().assemble(crossed)

    assert crossed.name == "trend_ema_rsi_entry_x_momentum_breakout_exit"
    assert strategy.entry.describe() == "ema_12 ↑ cross ema_26"
    assert strategy.exit.describe() == "activity_trade_count_rolling_168 <= 0"
    # 過濾留在進場那一側，時間規則跟著出場走
    assert strategy.filters.describe() == "NOT rsi_14 > 70"
    assert strategy.holding.maximum_holding_bars == 24


def test_crossing_merges_the_feature_lists_without_duplicates():
    crossed = load("momentum_breakout").with_exit_from(load("momentum_breakout"))

    described = [specification.describe() for specification in crossed.features]

    assert len(described) == len(set(described))
    assert len(described) == len(load("momentum_breakout").features)


def test_a_crossed_configuration_still_passes_the_feature_reconciliation():
    """換掉一半之後，新的出場條件要讀的欄位也必須在合併後的特徵清單裡。"""
    crossed = load("mean_reversion_vwap").with_exit_from(load("trend_ema_rsi"))

    strategy = assembly().assemble(crossed)

    assert {"ema_12", "ema_26"} <= strategy.required_features
