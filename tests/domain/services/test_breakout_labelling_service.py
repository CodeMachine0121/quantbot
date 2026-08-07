import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.breakout import Breakout
from quantbot.domain.services.breakout_labelling_service import (
    BreakoutLabellingService,
)
from quantbot.domain.services.breakout_statistics_service import (
    BreakoutStatisticsService,
)
from quantbot.domain.values.breakout_label import BreakoutLabel
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(highs, lows) -> MarketView:
    highs = np.asarray(highs, dtype="float64")
    lows = np.asarray(lows, dtype="float64")
    closes = (highs + lows) / 2
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


def test_a_breakout_that_keeps_going_is_held():
    #        0     1     2     3(突破)  4     5     6
    highs = [10.0, 11.0, 12.0, 20.0, 22.0, 24.0, 26.0]
    lows = [9.0, 10.0, 11.0, 19.0, 21.0, 23.0, 25.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )

    assert len(labels) == 1
    assert labels[BreakoutLabellingService.LABEL_COLUMN].iloc[0] == (
        BreakoutLabel.HELD.value
    )


def test_a_breakout_that_falls_back_below_the_level_failed():
    #        0     1     2     3(突破)  4     5     6
    highs = [10.0, 11.0, 12.0, 20.0, 19.0, 18.0, 17.0]
    # 被突破的價位是前高 12。第 5 根的低點跌到 11，回到突破前的區間裡。
    lows = [9.0, 10.0, 11.0, 19.0, 15.0, 11.0, 13.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )

    assert labels[BreakoutLabellingService.LABEL_COLUMN].iloc[0] == (
        BreakoutLabel.FAILED.value
    )


def test_the_forward_window_excludes_the_breakout_bar_itself():
    """突破那一根自己的低點不算「跌回來」。

    這一根的低點幾乎一定在突破價位之下（它就是那根 K 線的下緣），所以把它算進去
    的話每一次突破都會被標成失敗。這是這個 service 最容易寫錯的一格。
    """
    highs = [10.0, 11.0, 12.0, 20.0, 21.0, 22.0, 23.0]
    lows = [9.0, 10.0, 11.0, 5.0, 20.5, 21.5, 22.5]  # 突破那根自己有很長的下影線
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )

    assert labels[BreakoutLabellingService.LABEL_COLUMN].iloc[0] == (
        BreakoutLabel.HELD.value
    )


def test_events_without_a_complete_forward_window_are_dropped():
    """最後幾根還沒有未來，不能給它們標籤。"""
    highs = [10.0, 11.0, 12.0, 20.0, 21.0]
    lows = [9.0, 10.0, 11.0, 19.0, 20.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=5).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )

    assert labels.empty


def test_excursions_are_measured_from_the_broken_level():
    """幅度是從**被突破的價位**（前高 12）算的，不是從突破那根的高點。"""
    #        0     1     2     3(突破)  4     5     6
    highs = [10.0, 11.0, 12.0, 20.0, 26.0, 24.0, 23.0]
    lows = [9.0, 10.0, 11.0, 19.0, 18.0, 10.0, 21.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )
    row = labels.iloc[0]

    assert row[BreakoutLabellingService.FAVOURABLE_COLUMN] == pytest.approx(14.0)
    assert row[BreakoutLabellingService.ADVERSE_COLUMN] == pytest.approx(2.0)
    assert row[BreakoutLabellingService.LABEL_COLUMN] == BreakoutLabel.FAILED.value


def test_a_breakout_that_never_retraces_has_zero_adverse_excursion():
    """完全沒有回檔的突破，逆行幅度是 0 而不是負數。"""
    highs = [10.0, 11.0, 12.0, 20.0, 22.0, 24.0, 26.0]
    lows = [9.0, 10.0, 11.0, 19.0, 21.0, 23.0, 25.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.HIGH, window=3)
    )

    assert labels[BreakoutLabellingService.ADVERSE_COLUMN].iloc[0] == pytest.approx(0.0)


def test_low_side_labels_mirror_the_high_side():
    highs = [20.0, 19.0, 18.0, 12.0, 11.0, 10.0, 9.0]
    lows = [19.0, 18.0, 17.0, 10.0, 9.0, 8.0, 7.0]
    view = make_view(highs, lows)

    labels = BreakoutLabellingService(horizon=3).label(
        view, Breakout(side=ExtremeSide.LOW, window=3)
    )

    assert labels[BreakoutLabellingService.LABEL_COLUMN].iloc[0] == (
        BreakoutLabel.HELD.value
    )


def test_statistics_contrast_only_uses_what_was_observable():
    """統計服務只吃已經對齊好的兩張表，它不知道那些量是怎麼算出來的。"""
    highs = np.concatenate([np.arange(10.0, 40.0), np.arange(39.0, 20.0, -1.0)])
    lows = highs - 1.0
    view = make_view(highs, lows)
    breakout = Breakout(side=ExtremeSide.HIGH, window=5)
    labelling = BreakoutLabellingService(horizon=3)
    labels = labelling.label(view, breakout)

    report = BreakoutStatisticsService().summarize(
        labels,
        {"excess": breakout.excess(view)},
        horizon=labelling.horizon,
    )

    assert report.event_count == len(labels)
    assert report.held_count + report.failed_count == report.event_count
    assert 0.0 <= report.held_ratio <= 1.0
    assert report.contrasts[0].name == "excess"


def test_rejects_a_non_positive_horizon():
    with pytest.raises(ValueError):
        BreakoutLabellingService(horizon=0)
