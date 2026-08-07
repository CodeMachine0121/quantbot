import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.services.candle_agreement_service import CandleAgreementService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)


def make_candles(count: int = 5, *, close_offset: float = 0.0) -> CandleSeries:
    index = pd.date_range(
        "2026-07-15", periods=count, freq="1min", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5 + close_offset,
                "volume": 10.0,
                "quote_volume": 1005.0,
                "taker_buy_base_volume": 4.0,
                "taker_buy_quote_volume": 402.0,
                "trade_count": 7,
            },
            index=index,
        ),
    )


def test_identical_series_agree():
    report = CandleAgreementService().compare(make_candles(), make_candles())

    assert report.compared_bar_count == 5
    assert report.passed
    assert max(report.maximum_relative_difference.values()) == 0.0


def test_a_single_wrong_column_shows_up_as_the_worst_column():
    """欄位對映錯一格的症狀：一欄的誤差比其他欄大好幾個數量級。"""
    official = make_candles()
    rebuilt = make_candles()
    rebuilt.frame.loc[rebuilt.open_times[2], "volume"] = 999.0

    report = CandleAgreementService().compare(rebuilt, official)

    assert not report.passed
    assert report.worst_column == "volume"
    assert report.maximum_relative_difference["volume"] == pytest.approx(98.9)


def test_missing_bars_are_counted_on_both_sides():
    official = make_candles(5)
    rebuilt = CandleSeries(INSTRUMENT, official.frame.iloc[:3])

    report = CandleAgreementService().compare(rebuilt, official)

    assert report.compared_bar_count == 3
    assert report.missing_in_rebuilt == 2
    assert report.missing_in_official == 0
    assert not report.passed


def test_zero_scale_falls_back_to_absolute_difference():
    """成交量在冷清的一分鐘真的會是 0，用相對誤差會變成 0/0。"""
    official = make_candles(1)
    official.frame.loc[:, "volume"] = 0.0
    rebuilt = make_candles(1)
    rebuilt.frame.loc[:, "volume"] = 0.0

    report = CandleAgreementService().compare(rebuilt, official)

    assert report.maximum_relative_difference["volume"] == 0.0
    assert report.passed


def test_no_shared_bars_never_counts_as_a_pass():
    """兩邊完全對不上的時候，NEVER 因為「沒有誤差」而通過。"""
    official = make_candles(3)
    shifted = CandleSeries(
        INSTRUMENT, official.frame.set_index(official.open_times + pd.Timedelta(days=1))
    )

    report = CandleAgreementService().compare(shifted, official)

    assert report.compared_bar_count == 0
    assert not report.passed


def test_tolerance_allows_floating_point_noise():
    report = CandleAgreementService(tolerance=1e-6).compare(
        make_candles(close_offset=1e-9), make_candles()
    )

    assert report.passed
