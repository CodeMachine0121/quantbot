import pytest

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.search_space_service import SearchSpaceService
from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.search_space import (
    ConditionParameterAxis,
    ConditionTree,
    FeatureParameterAxis,
    IncreasingPeriodConstraint,
    SearchSpace,
)
from quantbot.domain.values.strategy_specification import StrategySpecification


def service() -> SearchSpaceService:
    return SearchSpaceService(features=FeatureRegistry())


def base() -> StrategySpecification:
    return StrategySpecification(
        name="trend",
        features=(
            FeatureSpecification(kind="ema", parameters={"period": 12}),
            FeatureSpecification(kind="ema", parameters={"period": 26}),
            FeatureSpecification(kind="rsi", parameters={"period": 14}),
        ),
        entry=ConditionSpecification(
            kind="crossover",
            parameters={"fast": "ema_12", "direction": "up", "slow": "ema_26"},
        ),
        exit=ConditionSpecification(
            kind="crossover",
            parameters={"fast": "ema_12", "direction": "down", "slow": "ema_26"},
        ),
        filters=ConditionSpecification(
            kind="not",
            children=(
                ConditionSpecification(
                    kind="threshold",
                    parameters={
                        "feature": "rsi_14",
                        "comparison": "above",
                        "value": 70,
                    },
                ),
            ),
        ),
    )


def test_the_combination_count_is_the_product_of_the_axes():
    space = SearchSpace(
        base=base(),
        axes=(
            FeatureParameterAxis(feature_index=0, key="period", values=(8, 12)),
            ConditionParameterAxis(
                tree=ConditionTree.FILTERS, key="value", values=(65, 70, 75)
            ),
        ),
    )

    assert space.unconstrained_combination_count == 6
    assert len(service().expand(space)) == 6


def test_changing_a_feature_parameter_rewrites_the_condition_references():
    """改了 period 就改了特徵的名字，而條件引用的是名字。"""
    space = SearchSpace(
        base=base(),
        axes=(FeatureParameterAxis(feature_index=0, key="period", values=(8,)),),
    )

    expanded = service().expand(space)[0]

    assert expanded.features[0].parameters["period"] == 8
    assert expanded.entry.parameters["fast"] == "ema_8"
    assert expanded.exit.parameters["fast"] == "ema_8"
    # 沒有被改到的那一邊要保持原樣
    assert expanded.entry.parameters["slow"] == "ema_26"


def test_a_condition_axis_rewrites_the_parameter_deep_in_the_tree():
    space = SearchSpace(
        base=base(),
        axes=(
            ConditionParameterAxis(
                tree=ConditionTree.FILTERS, key="value", values=(65,)
            ),
        ),
    )

    filters = service().expand(space)[0].filters

    assert filters is not None
    assert filters.children[0].parameters["value"] == 65


def test_combinations_that_do_not_make_sense_are_pruned():
    """快線週期比慢線長不是「比較差的策略」，是講不通的策略。"""
    space = SearchSpace(
        base=base(),
        axes=(
            FeatureParameterAxis(feature_index=0, key="period", values=(8, 21, 34)),
            FeatureParameterAxis(feature_index=1, key="period", values=(21, 26)),
        ),
        constraints=(
            IncreasingPeriodConstraint(faster_feature_index=0, slower_feature_index=1),
        ),
    )

    expanded = service().expand(space)

    # 6 種裡只有 (8,21) (8,26) (21,26) 講得通
    assert space.unconstrained_combination_count == 6
    assert len(expanded) == 3
    assert service().pruned_count(space) == 3


def test_every_expanded_specification_has_a_name_that_points_back_to_its_parameters():
    space = SearchSpace(
        base=base(),
        axes=(FeatureParameterAxis(feature_index=0, key="period", values=(8, 12)),),
    )

    names = [expanded.name for expanded in service().expand(space)]

    assert names == ["trend__period8", "trend__period12"]
    assert len(set(names)) == len(names)


def test_pruning_everything_is_an_error_not_an_empty_result():
    space = SearchSpace(
        base=base(),
        axes=(FeatureParameterAxis(feature_index=0, key="period", values=(34,)),),
        constraints=(
            IncreasingPeriodConstraint(faster_feature_index=0, slower_feature_index=1),
        ),
    )

    with pytest.raises(ValueError, match="一個組合都不剩"):
        service().expand(space)


def test_an_axis_pointing_past_the_feature_list_fails_with_a_readable_message():
    space = SearchSpace(
        base=base(),
        axes=(FeatureParameterAxis(feature_index=9, key="period", values=(8,)),),
    )

    with pytest.raises(ValueError, match="只有 3 個"):
        service().expand(space)


def test_an_empty_axis_or_an_empty_space_is_rejected():
    with pytest.raises(ValueError, match="至少要有一個值"):
        FeatureParameterAxis(feature_index=0, key="period", values=())
    with pytest.raises(ValueError, match="至少要有一個軸"):
        SearchSpace(base=base(), axes=())
