import pytest

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.constant_condition import Always
from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.holding_rules import HoldingRules
from quantbot.domain.values.position_direction import PositionDirection
from quantbot.domain.values.strategy_specification import StrategySpecification


def service() -> StrategyAssemblyService:
    return StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )


def crossing() -> ConditionSpecification:
    return ConditionSpecification(
        kind="crossover",
        parameters={"fast": "ema_12", "direction": "up", "slow": "ema_26"},
    )


def falling() -> ConditionSpecification:
    return ConditionSpecification(
        kind="crossover",
        parameters={"fast": "ema_12", "direction": "down", "slow": "ema_26"},
    )


def specification(**overrides: object) -> StrategySpecification:
    defaults: dict[str, object] = {
        "name": "trend",
        "features": (
            FeatureSpecification(kind="ema", parameters={"period": 12}),
            FeatureSpecification(kind="ema", parameters={"period": 26}),
        ),
        "entry": crossing(),
        "exit": falling(),
    }
    defaults.update(overrides)
    return StrategySpecification(**defaults)  # type: ignore[arg-type]


def test_assembling_builds_all_three_trees():
    strategy = service().assemble(specification())

    assert strategy.name == "trend"
    assert strategy.entry.describe() == "ema_12 ↑ cross ema_26"
    assert strategy.exit.describe() == "ema_12 ↓ cross ema_26"
    assert isinstance(strategy.filters, Always)


def test_a_condition_referencing_an_undeclared_feature_fails_at_assembly():
    """把 ema_12 寫成 ema12 的設定檔會照樣跑完、照樣產出報告，
    而那個條件從第一根到最後一根都不成立。這道檢查就是為了擋它。"""
    typo = ConditionSpecification(
        kind="crossover",
        parameters={"fast": "ema12", "direction": "up", "slow": "ema_26"},
    )

    with pytest.raises(ValueError, match="沒有宣告的欄位"):
        service().assemble(specification(entry=typo))


def test_candle_columns_count_as_declared_without_being_features():
    """收盤價不是特徵，它是原料。條件要拿它跟 VWAP 比，所以它必須算已宣告。"""
    against_vwap = ConditionSpecification(
        kind="compare",
        parameters={"left": "close", "comparison": "above", "right": "vwap_session"},
    )

    strategy = service().assemble(
        specification(
            features=(
                FeatureSpecification(kind="vwap", parameters={"mode": "session"}),
            ),
            entry=against_vwap,
            exit=ConditionSpecification(
                kind="compare",
                parameters={
                    "left": "close",
                    "comparison": "below",
                    "right": "vwap_session",
                },
            ),
        )
    )

    assert "close" in strategy.required_features


def test_available_columns_lists_features_and_candle_columns():
    columns = service().available_columns(specification())

    assert {"ema_12", "ema_26"} <= columns
    assert {"close", "high", "low", "volume"} <= columns


def test_holding_rules_and_direction_pass_through_unchanged():
    strategy = service().assemble(
        specification(
            holding=HoldingRules(maximum_holding_bars=48, cooldown_bars=12),
            direction=PositionDirection.SHORT,
        )
    )

    assert strategy.holding.maximum_holding_bars == 48
    assert strategy.holding.cooldown_bars == 12
    assert strategy.direction is PositionDirection.SHORT


def test_a_broken_feature_specification_fails_before_the_features_are_computed():
    with pytest.raises(ValueError, match="未知的特徵"):
        service().assemble(specification(features=(FeatureSpecification(kind="emma"),)))
