"""同一個策略的三種寫法，逐根產生完全相同的部位序列。

這個測試比任何說明都有力：純 Python（tests/reference/）、積木運算子、YAML 設定檔，
三者如果有任何一根不一樣，就表示引擎或載入器其中一個理解錯了。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.crossover_condition import Crossover
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.strategies.threshold_condition import Threshold
from quantbot.domain.values.comparison import Comparison
from quantbot.domain.values.cross_direction import CrossDirection
from quantbot.infrastructure.configuration.yaml_strategy_specification_loader import (
    YamlStrategySpecificationLoader,
)
from tests.reference.reference_trend_following import ReferenceTrendFollowing

CONFIGURATION = (
    Path(__file__).resolve().parents[3]
    / "quantbot"
    / "infrastructure"
    / "configuration"
    / "strategies"
    / "trend_ema_rsi.yaml"
)


def make_table(bar_count: int = 1500, seed: int = 17) -> pd.DataFrame:
    """一段有趨勢也有震盪的合成價格，配上真的算出來的 EMA 與 RSI。

    合成而不是取真實資料，是為了讓測試不依賴資料庫；用亂數走勢而不是手寫十根，
    是因為交叉與過濾的組合要夠多才問得出「三種寫法真的一樣嗎」。

    參數是挑過的：這段資料有 21 次向上交叉，其中 2 次發生在 RSI 已經超過 70 的
    時候。少了後者，最後一個測試就證明不了過濾條件真的被讀進來。
    """
    generator = np.random.default_rng(seed)
    steps = generator.normal(loc=0.0, scale=0.015, size=bar_count)
    trend = np.sin(np.linspace(0, 30 * np.pi, bar_count)) * 0.005
    close = 100.0 * np.exp(np.cumsum(steps + trend))
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    prices = pd.Series(close, index=index)

    fast = prices.ewm(span=12, adjust=False).mean()
    slow = prices.ewm(span=26, adjust=False).mean()
    change = prices.diff()
    gain = change.clip(lower=0.0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-change.clip(upper=0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    strength = 100.0 - 100.0 / (1.0 + gain / loss)

    return pd.DataFrame(
        {
            "close": prices,
            "ema_12": fast,
            "ema_26": slow,
            "rsi_14": strength,
        }
    )


def blocks_strategy() -> Strategy:
    entry = Crossover("ema_12", CrossDirection.UP, "ema_26")
    exit_ = Crossover("ema_12", CrossDirection.DOWN, "ema_26")
    return Strategy(
        name="trend_ema_rsi",
        entry=entry,
        exit=exit_,
        filters=~Threshold("rsi_14", Comparison.ABOVE, 70.0),
    )


def loaded_strategy() -> Strategy:
    specification = YamlStrategySpecificationLoader().load(CONFIGURATION)
    assembly = StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )
    return assembly.assemble(specification)


def test_plain_python_and_blocks_agree_bar_by_bar():
    table = make_table()
    engine = StrategyEngine()

    reference = ReferenceTrendFollowing().positions(table)
    blocks = engine.positions(blocks_strategy(), table)

    assert reference.tolist() == blocks.tolist()
    # 這段資料真的有交易，不是兩邊都全空手所以「相同」
    assert blocks.sum() > 0


def test_the_yaml_configuration_produces_the_same_positions():
    table = make_table()
    engine = StrategyEngine()

    blocks = engine.positions(blocks_strategy(), table)
    loaded = engine.positions(loaded_strategy(), table)

    assert blocks.tolist() == loaded.tolist()


def test_the_shipped_configuration_describes_the_same_tree_as_the_blocks():
    assert loaded_strategy().describe() == blocks_strategy().describe()


def test_the_filter_actually_removes_entries_in_this_data():
    """如果過濾條件在這段資料上什麼都沒擋，上面兩個測試就證明不了它有被讀進來。"""
    table = make_table()
    engine = StrategyEngine()

    unfiltered = Strategy(
        name="trend_ema_rsi",
        entry=Crossover("ema_12", CrossDirection.UP, "ema_26"),
        exit=Crossover("ema_12", CrossDirection.DOWN, "ema_26"),
    )
    with_filter = engine.signals(blocks_strategy(), table)
    without_filter = engine.signals(unfiltered, table)

    assert with_filter.vetoed_entry_count > 0
    assert with_filter.trade_count < without_filter.trade_count
