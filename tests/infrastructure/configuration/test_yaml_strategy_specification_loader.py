from pathlib import Path

import pytest

from quantbot.domain.values.position_direction import PositionDirection
from quantbot.infrastructure.configuration.yaml_strategy_specification_loader import (
    YamlStrategySpecificationLoader,
)

SHIPPED = (
    Path(__file__).resolve().parents[3]
    / "quantbot"
    / "infrastructure"
    / "configuration"
    / "strategies"
)

MINIMAL = """
name: minimal
features:
  - kind: ema
    period: 12
entry:
  kind: always
exit:
  kind: never
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "strategy.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def load(tmp_path: Path, text: str):
    return YamlStrategySpecificationLoader().load(write(tmp_path, text))


def test_the_shipped_configuration_loads():
    """跑不起來的文件比沒有文件糟，所以內附的設定檔要有測試守著。"""
    specification = YamlStrategySpecificationLoader().load(
        SHIPPED / "trend_ema_rsi.yaml"
    )

    assert specification.name == "trend_ema_rsi"
    assert len(specification.features) == 3
    assert specification.entry.kind == "crossover"
    assert specification.filters is not None
    assert specification.filters.kind == "not"
    assert specification.filters.children[0].kind == "threshold"


def test_a_minimal_configuration_defaults_filters_holding_and_direction(tmp_path):
    specification = load(tmp_path, MINIMAL)

    assert specification.filters is None
    assert specification.holding.maximum_holding_bars is None
    assert specification.holding.cooldown_bars is None
    assert specification.direction is PositionDirection.LONG


def test_holding_rules_are_read_when_present(tmp_path):
    specification = load(
        tmp_path,
        MINIMAL + "holding:\n  maximum_holding_bars: 48\n  cooldown_bars: 12\n",
    )

    assert specification.holding.maximum_holding_bars == 48
    assert specification.holding.cooldown_bars == 12


def test_an_unknown_holding_field_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="holding 有不認識的欄位"):
        load(tmp_path, MINIMAL + "holding:\n  maximum_bars: 48\n")


WITHOUT = {
    "name": "features:\n  - kind: ema\n    period: 12\nentry:\n  kind: always\n"
    "exit:\n  kind: never\n",
    "features": "name: minimal\nentry:\n  kind: always\nexit:\n  kind: never\n",
    "entry": "name: minimal\nfeatures:\n  - kind: ema\n    period: 12\n"
    "exit:\n  kind: never\n",
    "exit": "name: minimal\nfeatures:\n  - kind: ema\n    period: 12\n"
    "entry:\n  kind: always\n",
}


@pytest.mark.parametrize("missing", sorted(WITHOUT))
def test_every_required_key_is_checked(tmp_path, missing):
    with pytest.raises(ValueError, match=missing):
        load(tmp_path, WITHOUT[missing])


def test_of_is_rejected_on_a_leaf_kind(tmp_path):
    text = MINIMAL.replace(
        "entry:\n  kind: always",
        "entry:\n  kind: always\n  of:\n    - kind: never",
    )

    with pytest.raises(ValueError, match="不能有 of"):
        load(tmp_path, text)


def test_a_non_scalar_parameter_is_rejected_where_it_is_written(tmp_path):
    text = MINIMAL.replace(
        "entry:\n  kind: always",
        "entry:\n  kind: threshold\n  feature: rsi_14\n"
        "  comparison: above\n  value:\n    - 70",
    )

    with pytest.raises(ValueError, match="只能是數字或字串"):
        load(tmp_path, text)


def test_an_illegal_direction_lists_the_legal_values(tmp_path):
    with pytest.raises(ValueError, match="direction 只能是"):
        load(tmp_path, MINIMAL + "direction: sideways\n")


def test_nested_composites_keep_their_order(tmp_path):
    text = MINIMAL.replace(
        "entry:\n  kind: always",
        """entry:
  kind: all
  of:
    - kind: threshold
      feature: rsi_14
      comparison: below
      value: 70
    - kind: any
      of:
        - kind: event
          feature: breakout_high_20
        - kind: never
""",
    )

    entry = load(tmp_path, text).entry

    assert entry.kind == "all"
    assert entry.children[0].kind == "threshold"
    assert entry.children[1].kind == "any"
    assert [child.kind for child in entry.children[1].children] == ["event", "never"]
