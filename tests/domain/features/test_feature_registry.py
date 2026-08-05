import pytest

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.feature_specification import FeatureSpecification

REGISTRY = FeatureRegistry()


def test_every_kind_is_reachable_by_string():
    """設定檔只寫字串，所以每一個 kind 都必須查得到。"""
    assert set(REGISTRY.kinds()) == set(REGISTRY.BUILDERS)
    assert "obi" in REGISTRY.kinds()
    assert "distance_to_poc" in REGISTRY.kinds()


def test_every_builder_can_be_built_with_only_its_required_parameters():
    """走過整張註冊表，確認每個 kind 都建得起來。

    這個測試的價值在於它會抓到「新增一個 builder 但參數的預設值忘記給」——
    那種錯誤要等到有人在設定檔裡用到那個 kind 才會出現。
    """
    required_period = {"sma", "ema", "rsi"}
    for kind in REGISTRY.kinds():
        specification = FeatureSpecification(
            kind, {"period": 14} if kind in required_period else {}
        )
        feature = REGISTRY.build(specification)

        assert feature.name
        assert feature.warmup_bar_count >= 0
        assert feature.required_inputs


def test_an_unknown_kind_lists_the_available_ones():
    with pytest.raises(ValueError, match="可用"):
        REGISTRY.build(FeatureSpecification("mystery_signal"))


def test_a_misspelled_parameter_is_rejected_not_ignored():
    """這是這個註冊表最重要的一條。

    安靜忽略的話，使用者以為自己在跑 period=50，實際上跑的是預設值。
    """
    with pytest.raises(ValueError, match="沒有被使用的參數"):
        REGISTRY.build(FeatureSpecification("rsi", {"period": 14, "perid": 50}))


def test_an_illegal_enum_value_lists_the_legal_ones():
    with pytest.raises(ValueError, match="mean"):
        REGISTRY.build(FeatureSpecification("obi", {"aggregation": "medain"}))


def test_build_all_names_the_offending_line():
    """整份設定有一行壞掉時，錯誤訊息要指名是哪一行。"""
    with pytest.raises(ValueError, match=r"obi\(depth_level=7\)"):
        REGISTRY.build_all(
            (
                FeatureSpecification("ema", {"period": 12}),
                FeatureSpecification("obi", {"depth_level": 7}),
            )
        )


def test_build_all_is_all_or_nothing():
    """「算出一半的特徵」沒有用，所以任何一行有問題就整份失敗。"""
    with pytest.raises(ValueError):
        REGISTRY.build_all(
            (
                FeatureSpecification("ema", {"period": 12}),
                FeatureSpecification("nope"),
            )
        )


def test_indicator_kinds_share_one_builder_but_produce_different_features():
    fast = REGISTRY.build(FeatureSpecification("ema", {"period": 12}))
    slow = REGISTRY.build(FeatureSpecification("sma", {"period": 60}))

    assert fast.name == "ema_12"
    assert slow.name == "sma_60"


def test_parameters_convert_strings_from_yaml():
    """YAML 的 `period: "14"` 是字串，而它應該可以用。"""
    parameters = FeatureParameters(values={"period": "14"})

    assert parameters.integer("period") == 14


def test_parameters_reject_a_non_integer():
    parameters = FeatureParameters(values={"period": 14.5})

    with pytest.raises(ValueError, match="整數"):
        parameters.integer("period")


def test_parameters_reject_a_boolean_pretending_to_be_a_number():
    """Python 的 bool 是 int 的子類別，所以 True 會安靜地變成 1。"""
    parameters = FeatureParameters(values={"period": True})

    with pytest.raises(ValueError):
        parameters.integer("period")


def test_a_missing_required_parameter_is_named():
    with pytest.raises(ValueError, match="period"):
        FeatureParameters().integer("period")
