import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.volume_weighted_average_price import VWAP
from quantbot.domain.features.vwap_deviation import VWAPDeviation
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.price_source import PriceSource
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.vwap_mode import VWAPMode

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(
    *,
    closes: list[float] | np.ndarray,
    volumes: list[float] | np.ndarray | None = None,
    highs: list[float] | np.ndarray | None = None,
    lows: list[float] | np.ndarray | None = None,
    start: str = "2026-07-15",
    freq: str = "1h",
) -> MarketView:
    closes = np.asarray(closes, dtype="float64")
    index = pd.date_range(
        start, periods=len(closes), freq=freq, tz="UTC", name="open_time"
    )
    return MarketView(
        candles=CandleSeries(
            INSTRUMENT,
            pd.DataFrame(
                {
                    "open": closes,
                    "high": closes if highs is None else np.asarray(highs),
                    "low": closes if lows is None else np.asarray(lows),
                    "close": closes,
                    "volume": (
                        np.ones(len(closes)) if volumes is None else np.asarray(volumes)
                    ),
                },
                index=index,
            ),
        )
    )


def weighted_mean(values, weights) -> float:
    """照定義手算，只用來當對照組。"""
    values = np.asarray(values, dtype="float64")
    weights = np.asarray(weights, dtype="float64")
    return float((values * weights).sum() / weights.sum())


def test_volume_weighting_is_not_the_arithmetic_mean():
    """一顆與一百顆的成交不該一樣重要，這是 VWAP 存在的全部理由。"""
    view = make_view(closes=[100.0, 200.0], volumes=[1.0, 99.0])

    line = VWAP(price_source=PriceSource.CLOSE).compute(view)

    assert line.iloc[-1] == pytest.approx(199.0)  # 不是 150
    assert line.iloc[-1] == pytest.approx(weighted_mean([100, 200], [1, 99]))


def test_session_mode_resets_at_utc_midnight():
    """跨日要重置。不重置的話第二天的 VWAP 會被前一天的成交拖住。"""
    view = make_view(
        closes=[100.0] * 24 + [200.0] * 24,
        volumes=[1.0] * 48,
        start="2026-07-15",
        freq="1h",
    )

    line = VWAP(mode=VWAPMode.SESSION, price_source=PriceSource.CLOSE).compute(view)

    assert line.iloc[23] == pytest.approx(100.0)  # 第一天結束
    assert line.iloc[24] == pytest.approx(200.0)  # 第二天第一根，重新開始
    assert line.iloc[-1] == pytest.approx(200.0)  # 第二天結束，沒被前一天拉低


def test_session_mode_has_a_value_from_the_very_first_bar():
    view = make_view(closes=[100.0, 110.0], volumes=[1.0, 1.0])

    line = VWAP(mode=VWAPMode.SESSION).compute(view)

    assert line.notna().all()
    assert VWAP(mode=VWAPMode.SESSION).warmup_bar_count == 0


def test_rolling_mode_only_looks_back_a_fixed_window():
    view = make_view(closes=[100.0, 100.0, 100.0, 200.0], volumes=[1.0] * 4)
    feature = VWAP(mode=VWAPMode.ROLLING, window=2, price_source=PriceSource.CLOSE)

    line = feature.compute(view)

    assert pd.isna(line.iloc[0])  # 視窗還沒滿
    assert line.iloc[1] == pytest.approx(100.0)
    assert line.iloc[3] == pytest.approx(150.0)  # 只看最後兩根
    assert feature.warmup_bar_count == 1


def test_rolling_mode_ignores_the_day_boundary():
    """滾動模式不認識「一天」，所以跨日不會跳。"""
    view = make_view(closes=[100.0] * 48, volumes=[1.0] * 48)

    line = VWAP(mode=VWAPMode.ROLLING, window=24).compute(view)

    assert line.iloc[24] == pytest.approx(100.0)
    assert line.iloc[23:].notna().all()


def test_typical_price_uses_high_low_close():
    view = make_view(closes=[100.0], highs=[130.0], lows=[70.0], volumes=[1.0])

    typical = VWAP(price_source=PriceSource.TYPICAL).compute(view)
    close_only = VWAP(price_source=PriceSource.CLOSE).compute(view)

    assert typical.iloc[0] == pytest.approx(100.0)  # (130 + 70 + 100) / 3
    assert close_only.iloc[0] == pytest.approx(100.0)
    # 影線不對稱時兩者就會分家
    skewed = make_view(closes=[100.0], highs=[160.0], lows=[100.0], volumes=[1.0])
    assert VWAP(price_source=PriceSource.TYPICAL).compute(skewed).iloc[0] == (
        pytest.approx(120.0)
    )


def test_zero_volume_bars_are_nan_not_zero():
    """完全沒成交時平均成本沒有定義。填 0 會在圖上畫出一條掉到原點的線。"""
    view = make_view(closes=[100.0, 100.0], volumes=[0.0, 0.0])

    assert VWAP(mode=VWAPMode.SESSION).compute(view).isna().all()


def test_standard_deviation_matches_the_direct_computation():
    """加權變異數用「平方的平均 − 平均的平方」算，要跟直接展開的結果一致。"""
    generator = np.random.default_rng(20260925)
    closes = 65_000 + generator.normal(0, 40, 200)
    volumes = generator.uniform(0.1, 10.0, 200)
    # 用 1 分鐘讓 200 根全部落在同一天，日內模式才不會中途重置
    view = make_view(closes=closes, volumes=volumes, freq="1min")
    feature = VWAP(mode=VWAPMode.SESSION, price_source=PriceSource.CLOSE)

    computed = feature.standard_deviation(view).iloc[-1]

    average = weighted_mean(closes, volumes)
    direct = np.sqrt((volumes * (closes - average) ** 2).sum() / volumes.sum())
    assert computed == pytest.approx(direct, rel=1e-9)


def test_centring_keeps_the_precision_that_the_naive_identity_loses():
    """不平移的話，65,000 的平方跟變異數差八個數量級，有效位數會被吃掉。

    這裡把兩種寫法並排：平移過的版本跟直接展開的結果幾乎完全相同，
    沒平移的版本誤差大好幾個數量級。兩者都跑得出一個看起來合理的數字。
    """
    generator = np.random.default_rng(4)
    closes = 65_000 + generator.normal(0, 5, 500)  # 變異數小、價格大，最糟的情況
    volumes = generator.uniform(0.1, 5.0, 500)
    view = make_view(closes=closes, volumes=volumes, freq="1min")
    feature = VWAP(mode=VWAPMode.SESSION, price_source=PriceSource.CLOSE)

    average = weighted_mean(closes, volumes)
    direct = np.sqrt((volumes * (closes - average) ** 2).sum() / volumes.sum())

    centred_error = abs(feature.standard_deviation(view).iloc[-1] - direct)
    naive_variance = (
        weighted_mean(closes**2, volumes) - weighted_mean(closes, volumes) ** 2
    )
    naive_error = abs(np.sqrt(max(naive_variance, 0.0)) - direct)

    assert centred_error < 1e-9
    assert naive_error > centred_error * 100


def test_deviation_is_dimensionless_and_scales_with_distance():
    generator = np.random.default_rng(5)
    closes = 65_000 + generator.normal(0, 50, 300)
    view = make_view(closes=closes, volumes=generator.uniform(0.5, 5, 300), freq="1min")
    vwap = VWAP(mode=VWAPMode.SESSION, price_source=PriceSource.CLOSE)
    deviation = VWAPDeviation(vwap).compute(view)

    line = vwap.compute(view)
    spread = vwap.standard_deviation(view)
    # 第一根的加權標準差是 0（只有一個成交價），所以從第二根開始比
    expected = ((view.candles.frame["close"] - line) / spread).iloc[1:]

    assert pd.isna(deviation.iloc[0])
    assert np.allclose(deviation.iloc[1:], expected)
    assert deviation.name == "vwap_session_deviation"
    assert abs(deviation.iloc[-1]) < 6  # 標準化之後不該是幾百


def test_deviation_is_nan_when_there_is_only_one_price():
    """整段只有一個成交價時標準差是 0，偏離沒有定義。NEVER 回 inf。"""
    view = make_view(closes=[100.0] * 10, volumes=[1.0] * 10)

    deviation = VWAPDeviation(VWAP(mode=VWAPMode.SESSION)).compute(view)

    assert deviation.isna().all()


def test_names_distinguish_the_two_modes():
    assert VWAP(mode=VWAPMode.SESSION).name == "vwap_session"
    assert VWAP(mode=VWAPMode.ROLLING, window=48).name == "vwap_rolling_48"


def test_rejects_a_non_positive_window():
    with pytest.raises(ValueError):
        VWAP(mode=VWAPMode.ROLLING, window=0)
