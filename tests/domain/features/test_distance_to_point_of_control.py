import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.distance_to_point_of_control import (
    DistanceToPointOfControl,
)
from quantbot.domain.services.volume_profile_service import VolumeProfileService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(closes, volumes=None) -> MarketView:
    closes = np.asarray(closes, dtype="float64")
    index = pd.date_range(
        "2026-07-01", periods=len(closes), freq="1h", tz="UTC", name="open_time"
    )
    return MarketView(
        candles=CandleSeries(
            INSTRUMENT,
            pd.DataFrame(
                {
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": np.ones(len(closes)) if volumes is None else volumes,
                },
                index=index,
            ),
        )
    )


def test_the_window_excludes_the_current_bar():
    """每一根的 POC 只能用那根之前的資料算。

    用整段資料算一個 POC 再套到每一根上，是 Day 12 那個鐘點基準的錯誤換一種形狀。
    這裡的資料是：前 24 小時都成交在 100，第 25 根跳到 200。第 25 根的距離必須是
    +100%（相對於它之前的 POC 100），而不是 0%（相對於含它自己的 POC）。
    """
    closes = [100.0] * 24 + [200.0]
    view = make_view(closes)

    distance = DistanceToPointOfControl(window_days=1).compute(view)

    assert distance.iloc[-1] == pytest.approx(1.0)


def test_the_first_bars_have_no_history():
    view = make_view([100.0] * 10)

    distance = DistanceToPointOfControl(window_days=1).compute(view)

    assert pd.isna(distance.iloc[0])  # 第一根之前什麼都沒有
    assert distance.iloc[1:].notna().all()


def test_distance_is_relative_not_absolute():
    """除以 POC，所以它是無單位的，換一個價位量級也可比。"""
    cheap = make_view([100.0] * 24 + [110.0])
    expensive = make_view([100_000.0] * 24 + [110_000.0])
    feature = DistanceToPointOfControl(window_days=1)

    assert feature.compute(cheap).iloc[-1] == pytest.approx(
        feature.compute(expensive).iloc[-1]
    )


def test_output_contract():
    generator = np.random.default_rng(20260928)
    closes = 65_000 * np.exp(np.cumsum(generator.normal(0, 0.002, 100)))
    view = make_view(closes, volumes=generator.uniform(1, 20, 100))
    feature = DistanceToPointOfControl(window_days=2)

    values = feature.compute(view)

    assert values.index.equals(view.candles.frame.index)
    assert values.name == "distance_to_poc_2d"
    assert values.dtype == np.dtype("float64")
    assert feature.required_inputs == frozenset({MarketInput.CANDLES})


def test_a_custom_service_is_injectable():
    """分桶數會影響 POC，所以它是注入的，不是寫死的。"""
    closes = [100.0] * 24 + [150.0]
    view = make_view(closes)

    coarse = DistanceToPointOfControl(
        window_days=1, service=VolumeProfileService(bucket_count=2)
    ).compute(view)

    assert coarse.iloc[-1] == pytest.approx(0.5)


def test_rejects_a_non_positive_window():
    with pytest.raises(ValueError):
        DistanceToPointOfControl(window_days=0)
