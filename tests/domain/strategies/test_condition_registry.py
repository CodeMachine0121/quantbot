import pytest

from quantbot.domain.strategies.condition import AllOf, Not
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.crossover_condition import Crossover
from quantbot.domain.values.condition_specification import ConditionSpecification


def leaf(kind: str, **parameters: int | float | str) -> ConditionSpecification:
    return ConditionSpecification(kind=kind, parameters=parameters)


def test_a_leaf_specification_becomes_a_condition():
    built = ConditionRegistry().build(
        leaf("crossover", fast="ema_12", direction="up", slow="ema_26")
    )

    assert isinstance(built, Crossover)
    assert built.required_features == frozenset({"ema_12", "ema_26"})


def test_children_are_built_recursively():
    specification = ConditionSpecification(
        kind="all",
        children=(
            leaf("threshold", feature="rsi_14", comparison="below", value=70),
            ConditionSpecification(
                kind="not",
                children=(leaf("event", feature="breakout_high_20"),),
            ),
        ),
    )

    built = ConditionRegistry().build(specification)

    assert isinstance(built, AllOf)
    assert isinstance(built.conditions[1], Not)
    assert built.required_features == frozenset({"rsi_14", "breakout_high_20"})


def test_an_unknown_kind_lists_the_available_ones():
    with pytest.raises(ValueError, match="未知的條件"):
        ConditionRegistry().build(leaf("crossovr", fast="a", direction="up", slow="b"))


def test_a_misspelled_parameter_is_rejected_instead_of_ignored():
    """拼錯的參數名安靜被忽略，會讓使用者以為自己設了 60 其實跑的是預設值。"""
    with pytest.raises(ValueError, match="沒有被使用的參數"):
        ConditionRegistry().build(
            leaf("threshold", feature="rsi_14", comparison="below", value=70, perid=60)
        )


def test_an_illegal_enum_value_lists_the_legal_ones():
    with pytest.raises(ValueError, match="comparison 只能是"):
        ConditionRegistry().build(
            leaf("threshold", feature="rsi_14", comparison="abvoe", value=70)
        )


def test_a_leaf_kind_rejects_children():
    specification = ConditionSpecification(
        kind="event",
        parameters={"feature": "breakout_high_20"},
        children=(leaf("always"),),
    )

    with pytest.raises(ValueError, match="不接子節點"):
        ConditionRegistry().build(specification)


def test_not_takes_exactly_one_child():
    specification = ConditionSpecification(
        kind="not",
        children=(leaf("always"), leaf("never")),
    )

    with pytest.raises(ValueError, match="只能有一個子節點"):
        ConditionRegistry().build(specification)


def test_an_absurdly_deep_tree_fails_with_a_readable_message():
    """程式產生的設定檔（Day 21 的組合搜尋）可能巢得很深，
    而 RecursionError 對使用者毫無意義。"""
    specification = leaf("always")
    for _ in range(ConditionRegistry.MAXIMUM_DEPTH + 1):
        specification = ConditionSpecification(kind="all", children=(specification,))

    with pytest.raises(ValueError, match="條件樹太深"):
        ConditionRegistry().build(specification)


def test_every_registered_kind_is_buildable_with_its_minimum_parameters():
    """走過整張註冊表，抓的是「加了 builder 但參數對不起來」。"""
    minimum: dict[str, ConditionSpecification] = {
        "threshold": leaf("threshold", feature="a", comparison="above", value=1),
        "compare": leaf("compare", left="a", comparison="above", right="b"),
        "crossover": leaf("crossover", fast="a", direction="up", slow="b"),
        "range": leaf("range", feature="a", lower=0, upper=1),
        "event": leaf("event", feature="a"),
        "always": leaf("always"),
        "never": leaf("never"),
        "all": ConditionSpecification(kind="all", children=(leaf("always"),)),
        "any": ConditionSpecification(kind="any", children=(leaf("always"),)),
        "not": ConditionSpecification(kind="not", children=(leaf("always"),)),
        "sustained": ConditionSpecification(
            kind="sustained", parameters={"bars": 2}, children=(leaf("always"),)
        ),
    }

    assert sorted(minimum) == sorted(ConditionRegistry().kinds())
    for specification in minimum.values():
        assert ConditionRegistry().build(specification) is not None
