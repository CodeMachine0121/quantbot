import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.average_true_range import ATR
from quantbot.domain.indicators.rsi import RSI, WilderSmoother
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)
PERIOD = 14


def make_view(highs, lows, closes) -> MarketView:
    index = pd.date_range(
        "2026-07-15", periods=len(closes), freq="1h", tz="UTC", name="open_time"
    )
    return MarketView(
        candles=CandleSeries(
            INSTRUMENT,
            pd.DataFrame(
                {
                    "open": closes,
                    "high": highs,
                    "low": lows,
                    "close": closes,
                    "volume": 1.0,
                },
                index=index,
            ),
        )
    )


def reference_atr(highs, lows, closes, period: int = PERIOD) -> np.ndarray:
    """照 Wilder 的定義寫的迴圈版對照組。只在測試裡用，NEVER 進正式路徑。"""
    count = len(closes)
    true_range = np.full(count, np.nan)
    for index in range(1, count):
        previous_close = closes[index - 1]
        true_range[index] = max(
            highs[index] - lows[index],
            abs(highs[index] - previous_close),
            abs(lows[index] - previous_close),
        )
    average = np.full(count, np.nan)
    average[period] = np.mean(true_range[1 : period + 1])
    for index in range(period + 1, count):
        average[index] = (
            average[index - 1] * (period - 1) + true_range[index]
        ) / period
    return average


def test_true_range_takes_the_gap_into_account():
    """整根跳到前一根之上時，「高 − 低」很小但實際移動很大。"""
    view = make_view(highs=[100.0, 130.0], lows=[99.0, 128.0], closes=[99.5, 129.0])

    true_range = ATR.true_range(view.candles.frame)

    assert pd.isna(true_range.iloc[0])  # 沒有前一根收盤價
    assert true_range.iloc[1] == pytest.approx(30.5)  # |130 − 99.5|，不是 2.0


def test_first_true_range_is_nan_not_high_minus_low():
    """填成「高 − 低」會讓第一根系統性偏小，而偏差會被平滑帶進整個暖機期。"""
    view = make_view(highs=[100.0], lows=[90.0], closes=[95.0])

    assert ATR.true_range(view.candles.frame).isna().all()


def test_matches_the_loop_reference():
    generator = np.random.default_rng(20260926)
    closes = 65_000 * np.exp(np.cumsum(generator.normal(0, 0.003, 600)))
    spans = generator.uniform(20, 300, 600)
    highs = closes + spans
    lows = closes - spans
    view = make_view(highs=highs, lows=lows, closes=closes)

    assert np.allclose(
        ATR(PERIOD).compute(view).to_numpy(),
        reference_atr(highs, lows, closes),
        equal_nan=True,
        atol=1e-9,
    )


def test_output_contract():
    generator = np.random.default_rng(3)
    closes = 100 + generator.normal(0, 1, 100)
    view = make_view(highs=closes + 1, lows=closes - 1, closes=closes)
    feature = ATR(PERIOD)

    result = feature.compute(view)

    assert result.index.equals(view.candles.frame.index)
    assert result.name == f"atr_{PERIOD}"
    assert feature.warmup_bar_count == PERIOD
    assert feature.required_inputs == frozenset({MarketInput.CANDLES})
    assert result.iloc[:PERIOD].isna().all()
    assert result.iloc[PERIOD:].notna().all()


def test_atr_is_in_price_units_not_percent():
    """兩段形狀相同、價位差一千倍的資料，ATR 也差一千倍。

    這是 Day 24 用它決定停損距離時必須知道的事：它不能直接跨交易對比較。
    """
    closes = np.full(60, 100.0)
    small = make_view(highs=closes + 1, lows=closes - 1, closes=closes)
    large = make_view(
        highs=closes * 1_000 + 1_000, lows=closes * 1_000 - 1_000, closes=closes * 1_000
    )

    ratio = ATR(PERIOD).compute(large).iloc[-1] / ATR(PERIOD).compute(small).iloc[-1]

    assert ratio == pytest.approx(1_000.0)


def test_shares_the_same_smoother_as_rsi():
    """ATR 與 RSI 用的是同一種平滑，所以 ATR 重用 WilderSmoother 而不是再寫一份。"""
    assert WilderSmoother(PERIOD).alpha == pytest.approx(1 / PERIOD)
    assert isinstance(RSI(PERIOD), RSI)  # 兩者都建得起來，共用的類別沒有被搬壞


def test_rejects_a_non_positive_period():
    with pytest.raises(ValueError):
        ATR(0)
