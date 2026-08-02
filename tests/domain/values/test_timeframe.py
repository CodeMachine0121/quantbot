# tests/domain/values/test_timeframe.py
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
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


def test_timeframe_rejects_unknown_value():
    with pytest.raises(ValueError):
        Timeframe("2m")


@pytest.mark.parametrize(
    ("timeframe_value", "expected_frequency"),
    [("1m", "1min"), ("1h", "1h"), ("1d", "1D")],
)
def test_timeframe_maps_to_pandas_frequency(timeframe_value, expected_frequency):
    assert Timeframe(timeframe_value).pandas_frequency == expected_frequency


def test_latest_closed_open_time_excludes_the_bar_in_progress():
    now = pd.Timestamp("2026-09-22 04:00:30", tz="UTC")
    assert Timeframe("1m").latest_closed_open_time(now) == pd.Timestamp(
        "2026-09-22 03:59", tz="UTC"
    )
