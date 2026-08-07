import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.features.candle_indicator_feature import CandleIndicatorFeature
from quantbot.domain.features.feature_pipeline import FeaturePipeline
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.indicators.rsi import RSI
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(bar_count: int = 200, *, with_depth: bool = False) -> MarketView:
    generator = np.random.default_rng(20260929)
    closes = 65_000 * np.exp(np.cumsum(generator.normal(0, 0.003, bar_count)))
    index = pd.date_range(
        "2026-07-01", periods=bar_count, freq="1h", tz="UTC", name="open_time"
    )
    candles = CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": closes,
                "high": closes * 1.002,
                "low": closes * 0.998,
                "close": closes,
                "volume": generator.uniform(1, 50, bar_count),
                "trade_count": generator.integers(500, 5_000, bar_count),
            },
            index=index,
        ),
    )
    depth = None
    if with_depth:
        moments = pd.DatetimeIndex(
            # tz 一定要給：K 線是 tz-aware 的，兩邊時區不一致的話 reindex 對不上，
            # 而結果是一整欄 NaN 而不是例外
            pd.date_range("2026-07-01", periods=bar_count * 60, freq="1min", tz="UTC"),
            name=DepthColumns.CAPTURED_AT,
        )
        frame = pd.DataFrame(
            {"best_bid_price": 63_000.0, "best_ask_price": 63_000.01}, index=moments
        )
        for level in DepthColumns.LEVELS:
            frame[DepthColumns.bid_quantity(level)] = 3.0
            frame[DepthColumns.ask_quantity(level)] = 1.0
        depth = DepthSeries(LISTING, frame)
    return MarketView(candles=candles, depth=depth)


def build(*specifications: FeatureSpecification) -> FeaturePipeline:
    return FeaturePipeline(FeatureRegistry().build_all(specifications))


def test_one_configuration_produces_one_aligned_table():
    view = make_view()
    pipeline = build(
        FeatureSpecification("ema", {"period": 12}),
        FeatureSpecification("rsi", {"period": 14}),
        FeatureSpecification("atr", {"period": 14}),
    )

    table = pipeline.compute(view)

    assert list(table.columns) == ["ema_12", "rsi_14", "atr_14"]
    assert table.index.equals(view.candles.frame.index)
    assert table.dtypes.eq("float64").all()


def test_the_indicator_adapter_produces_the_same_numbers_as_the_indicator():
    """轉接器 NEVER 改變數值，它只換一個參數型別。"""
    view = make_view()
    indicator = RSI(14)

    adapted = CandleIndicatorFeature(indicator).compute(view)

    assert adapted.equals(indicator.compute(view.candles))
    assert adapted.name == indicator.name


def test_required_inputs_is_the_union():
    pipeline = build(
        FeatureSpecification("ema", {"period": 12}),
        FeatureSpecification("obi", {"depth_level": 5}),
    )

    assert pipeline.required_inputs == frozenset(
        {MarketInput.CANDLES, MarketInput.DEPTH}
    )


def test_missing_inputs_fail_before_anything_is_computed():
    """缺原料要報錯，NEVER 算出一整欄 NaN——那會跟暖機期混在一起。"""
    pipeline = build(
        FeatureSpecification("ema", {"period": 12}),
        FeatureSpecification("obi", {"depth_level": 5}),
    )

    with pytest.raises(ValueError, match="缺少原料"):
        pipeline.compute(make_view())


def test_the_error_names_which_features_wanted_the_missing_input():
    pipeline = build(FeatureSpecification("obi", {"depth_level": 10}))

    with pytest.raises(ValueError, match="obi_10_mean"):
        pipeline.compute(make_view())


def test_depth_features_work_once_the_depth_is_there():
    view = make_view(bar_count=5, with_depth=True)
    pipeline = build(FeatureSpecification("obi", {"depth_level": 5}))

    table = pipeline.compute(view)

    assert table["obi_5_mean"].notna().all()
    assert table["obi_5_mean"].iloc[0] == pytest.approx(0.5)


def test_trimming_uses_the_first_fully_valid_row_not_the_declared_warmup():
    """宣告的暖機期只是下限，照它切會留下 NaN。"""
    view = make_view()
    pipeline = build(
        FeatureSpecification("ema", {"period": 12}),
        FeatureSpecification("activity", {"window": 60}),
    )

    trimmed = pipeline.trimmed(view)

    assert trimmed.notna().all().all()
    assert len(trimmed) < len(view.candles)
    assert len(trimmed) >= len(view.candles) - pipeline.declared_warmup_bar_count * 2


def test_trimming_keeps_holes_that_are_not_warmup():
    """掛單簿中間的空白不是暖機期，照 NaN 切會把整段資料切光。"""
    view = make_view(bar_count=10, with_depth=True)
    depth = view.require_depth()
    # 把中間三小時的深度挖掉，模擬錄製中斷
    kept = depth.frame.loc[
        (depth.captured_times < "2026-07-01T04:00")
        | (depth.captured_times >= "2026-07-01T07:00")
    ]
    holed = MarketView(candles=view.candles, depth=DepthSeries(LISTING, kept))
    pipeline = build(FeatureSpecification("obi", {"depth_level": 5}))

    trimmed = pipeline.trimmed(holed)

    assert len(trimmed) == 10  # 沒有被切光
    assert trimmed["obi_5_mean"].isna().sum() == 3  # 中間那三根還是 NaN


def test_duplicate_feature_names_are_rejected_at_construction():
    """兩個一樣的設定會同名，concat 之後互相蓋掉。"""
    with pytest.raises(ValueError, match="重複"):
        build(
            FeatureSpecification("ema", {"period": 12}),
            FeatureSpecification("ema", {"period": 12}),
        )


def test_an_empty_pipeline_is_rejected():
    with pytest.raises(ValueError):
        FeaturePipeline(())


def test_the_cache_means_a_feature_is_computed_once_per_view():
    class CountingFeature:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def name(self) -> str:
            return "counting"

        @property
        def warmup_bar_count(self) -> int:
            return 0

        @property
        def required_inputs(self) -> frozenset[MarketInput]:
            return frozenset({MarketInput.CANDLES})

        def compute(self, view: MarketView) -> pd.Series:
            self.calls += 1
            return view.candles.frame["close"].rename(self.name)

    feature = CountingFeature()
    pipeline = FeaturePipeline((feature,))
    view = make_view(bar_count=10)

    pipeline.compute(view)
    pipeline.compute(view)
    pipeline.trimmed(view)

    assert feature.calls == 1
