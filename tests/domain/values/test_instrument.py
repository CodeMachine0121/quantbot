# tests/domain/values/test_instrument.py
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


def test_instrument_derives_native_symbol_and_storage_key():
    assert INSTRUMENT.native_symbol == "BTCUSDT"
    assert INSTRUMENT.storage_key == "spot_BTCUSDT_1m"


def test_market_is_an_enumeration_not_a_string():
    with pytest.raises(ValueError):
        Instrument(
            symbol="BTC/USDT", market=Market("futures"), timeframe=Timeframe("1m")
        )
