from pathlib import Path

import pytest

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.infrastructure.configuration.yaml_feature_specification_loader import (
    YamlFeatureSpecificationLoader,
)

LOADER = YamlFeatureSpecificationLoader()
SHIPPED_CONFIGURATION = (
    Path(__file__).resolve().parents[3]
    / "quantbot"
    / "infrastructure"
    / "configuration"
    / "features.yaml"
)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "features.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_parameters_sit_beside_kind(tmp_path):
    path = write(
        tmp_path,
        """
        features:
          - kind: ema
            period: 12
          - kind: activity
            measure: trade_count
            window: 168
        """,
    )

    specifications = LOADER.load(path)

    assert [item.kind for item in specifications] == ["ema", "activity"]
    assert specifications[0].parameters == {"period": 12}
    assert specifications[1].parameters == {"measure": "trade_count", "window": 168}


def test_the_shipped_configuration_loads_and_builds():
    """專案內附的那份設定檔必須真的建得起來。

    它是文件也是範例，而一份跑不起來的範例比沒有範例更糟。
    """
    specifications = LOADER.load(SHIPPED_CONFIGURATION)
    features = FeatureRegistry().build_all(specifications)

    assert len(features) == len(specifications)
    assert len({feature.name for feature in features}) == len(features)


def test_a_missing_kind_names_the_offending_entry(tmp_path):
    path = write(
        tmp_path,
        """
        features:
          - kind: ema
            period: 12
          - period: 26
        """,
    )

    with pytest.raises(ValueError, match="第 2 項"):
        LOADER.load(path)


def test_a_missing_features_list_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="features"):
        LOADER.load(write(tmp_path, "defaults:\n  symbol: BTC/USDT\n"))


def test_a_nested_parameter_is_rejected(tmp_path):
    """參數只能是數字或字串。巢狀結構會讓「設定檔很淺」這個承諾破掉。"""
    path = write(
        tmp_path,
        """
        features:
          - kind: ema
            period:
              value: 12
        """,
    )

    with pytest.raises(ValueError, match="period"):
        LOADER.load(path)


def test_a_boolean_is_rejected(tmp_path):
    """YAML 的 true 會變成 Python 的 True，而 bool 是 int 的子類別。"""
    path = write(
        tmp_path,
        """
        features:
          - kind: ema
            period: true
        """,
    )

    with pytest.raises(ValueError):
        LOADER.load(path)
