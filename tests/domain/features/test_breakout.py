import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.breakout import Breakout
from quantbot.domain.features.prior_extreme import PriorExtreme
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(highs, lows=None, closes=None) -> MarketView:
    highs = np.asarray(highs, dtype="float64")
    lows = highs - 1.0 if lows is None else np.asarray(lows, dtype="float64")
    closes = (
        (highs + lows) / 2 if closes is None else np.asarray(closes, dtype="float64")
    )
    index = pd.date_range(
        "2026-07-01", periods=len(highs), freq="1h", tz="UTC", name="open_time"
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


def test_prior_extreme_excludes_the_current_bar():
    """這是今天最重要的一個測試。

    含當根的話，「當根高點大於前高」永遠不成立——當根的高點本來就是那個最大值的
    候選之一。症狀不是訊號變少，是訊號完全消失，而程式不會有任何異常。
    """
    view = make_view(highs=[10.0, 11.0, 12.0, 20.0])
    feature = PriorExtreme(side=ExtremeSide.HIGH, window=3)

    prior = feature.compute(view)

    assert pd.isna(prior.iloc[2])  # 前面只有兩根，視窗還沒滿
    assert prior.iloc[3] == pytest.approx(12.0)  # 前三根的最高是 12，不是 20
    # 含當根的寫法會得到 20，於是「20 > 前高」不成立
    including = view.candles.frame["high"].rolling(3).max()
    assert including.iloc[3] == pytest.approx(20.0)


def test_a_breakout_is_detected_when_the_high_exceeds_the_prior_high():
    view = make_view(highs=[10.0, 11.0, 12.0, 20.0, 13.0])
    events = Breakout(side=ExtremeSide.HIGH, window=3).events(view)

    assert events.tolist() == [False, False, False, True, False]


def test_the_naive_rolling_version_finds_nothing_at_all():
    """把 shift 寫掉的版本，在一段一路創新高的資料上找不到任何突破。

    這個測試的價值在於它示範了錯誤的**形狀**：不是數字錯，是事件消失。
    一個回傳空訊號的策略在回測上看起來只是「這段行情沒有機會」。
    """
    highs = np.arange(10.0, 40.0)  # 每一根都比前一根高
    view = make_view(highs=highs)

    correct = Breakout(side=ExtremeSide.HIGH, window=5).events(view)
    naive = view.candles.frame["high"] > view.candles.frame["high"].rolling(5).max()

    assert correct.sum() == len(highs) - 5  # 視窗滿了之後每一根都是突破
    assert naive.sum() == 0


def test_low_side_compares_in_the_other_direction():
    """跌破前低是「小於」。方向寫反的話會把每個高點標成跌破。"""
    view = make_view(highs=[20.0] * 5, lows=[10.0, 11.0, 12.0, 5.0, 13.0])

    events = Breakout(side=ExtremeSide.LOW, window=3).events(view)

    assert events.tolist() == [False, False, False, True, False]


def test_excess_measures_how_far_it_broke():
    """「突破 0.3」與「突破 300」是不同的事件，events() 把它們當成同一件事。"""
    view = make_view(highs=[10.0, 11.0, 12.0, 12.5, 30.0, 29.0])
    breakout = Breakout(side=ExtremeSide.HIGH, window=3)

    excess = breakout.excess(view)

    assert excess.iloc[3] == pytest.approx(0.5)  # 勉強擦過去
    assert excess.iloc[4] == pytest.approx(17.5)  # 大幅突破
    assert excess.iloc[5] == pytest.approx(0.0)  # 沒突破的是 0，不是負數
    assert pd.isna(excess.iloc[2])  # 暖機期是 NaN，不是 0


def test_output_is_float_not_bool():
    """Day 15 的管線會把所有特徵 concat 成一張表，bool 欄位會讓 dtype 變成 object。"""
    view = make_view(highs=np.arange(10.0, 30.0))
    values = Breakout(side=ExtremeSide.HIGH, window=5).compute(view)

    assert values.dtype == np.dtype("float64")
    assert set(values.dropna().unique()) <= {0.0, 1.0}


def test_prior_level_is_the_same_computation_the_events_use():
    """圖上的線與判斷用的門檻 MUST 是同一份計算。"""
    view = make_view(highs=np.arange(10.0, 30.0))
    breakout = Breakout(side=ExtremeSide.HIGH, window=5)

    assert breakout.prior_level(view).equals(
        PriorExtreme(side=ExtremeSide.HIGH, window=5).compute(view)
    )


def test_warmup_and_naming():
    breakout = Breakout(side=ExtremeSide.HIGH, window=20)

    assert breakout.name == "breakout_high_20"
    assert breakout.warmup_bar_count == 20
    assert PriorExtreme(side=ExtremeSide.LOW, window=20).name == "prior_low_20"


def test_rejects_a_non_positive_window():
    with pytest.raises(ValueError):
        PriorExtreme(side=ExtremeSide.HIGH, window=0)
