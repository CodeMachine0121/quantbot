# tests/domain/entities/test_candle_series.py
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)


def make_series(bar_count: int, *, start: str = "2026-01-01") -> CandleSeries:
    index = pd.date_range(
        start, periods=bar_count, freq="1min", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": [100.0 + i for i in range(bar_count)],
                "volume": 1.0,
            },
            index=index,
        ),
    )


def test_candle_series_conforms_columns_and_fills_missing_ones():
    series = make_series(3)
    assert list(series.frame.columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "trade_count",
    ]
    assert series.frame["trade_count"].dtype == "Int64"
    assert series.frame["quote_volume"].isna().all()


def test_merge_prefers_the_caller_on_overlap():
    archive = make_series(5)
    rest = CandleSeries(INSTRUMENT, archive.frame.assign(close=-1.0))
    merged = archive.merge(rest)

    assert len(merged) == 5
    assert merged.frame["close"].tolist() == archive.frame["close"].tolist()


def test_merge_rejects_a_different_instrument():
    other = Instrument(symbol="ETH/USDT", market=Market.SPOT, timeframe=Timeframe("1m"))
    with pytest.raises(ValueError):
        make_series(2).merge(CandleSeries(other, make_series(2).frame))


def test_restricted_to_is_half_open():
    series = make_series(10)
    period = TimeRange(series.open_times[2], series.open_times[5])
    restricted = series.restricted_to(period)

    assert len(restricted) == 3
    assert restricted.open_times[-1] == series.open_times[4]


def test_closed_only_drops_the_bar_in_progress():
    series = make_series(4)  # 00:00 .. 00:03
    now = pd.Timestamp("2026-01-01 00:03:20", tz="UTC")
    assert len(series.closed_only(now)) == 3


def test_resample_aggregates_each_column_by_its_own_rule():
    """聚合的五條規則各不相同：open 取第一、close 取最後、量相加。

    這是 Day 02 用來驗證「1m 聚合出來的日線＝官方日線」的那個方法。
    """
    minutes = pd.date_range(
        "2026-01-01", periods=120, freq="1min", tz="UTC", name="open_time"
    )
    minute_series = CandleSeries(
        Instrument(symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")),
        pd.DataFrame(
            {
                "open": range(120),
                "high": range(100, 220),
                "low": range(-120, 0),
                "close": range(1, 121),
                "volume": 1.0,
            },
            index=minutes,
        ),
    )

    hourly = minute_series.resample(Timeframe("1h"))

    assert len(hourly) == 2
    assert hourly.instrument.timeframe == Timeframe("1h")
    assert hourly.frame["open"].iloc[0] == 0  # 第一根的 open
    assert hourly.frame["close"].iloc[0] == 60  # 最後一根的 close
    assert hourly.frame["high"].iloc[0] == 159  # 區間最大
    assert hourly.frame["low"].iloc[0] == -120  # 區間最小
    assert hourly.frame["volume"].iloc[0] == 60  # 相加
