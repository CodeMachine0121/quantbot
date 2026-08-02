# tests/domain/services/test_candle_sanitation_service.py
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.services.candle_sanitation_service import CandleSanitationService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
NOW = pd.Timestamp("2026-09-22 04:00", tz="UTC")


def test_sanitation_drops_structurally_impossible_rows_and_flags_the_rest():
    index = pd.date_range(
        "2026-01-01", periods=5, freq="1min", tz="UTC", name="open_time"
    )
    candles = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 99.0, 104.0, 105.0],  # 第 3 列 high < low：致命
            "low": [99.0, 100.0, 103.0, 102.0, 89.0],
            "close": [100.5, 101.5, 102.5, 103.5, 90.0],  # 第 5 列 -13%：price_jump
            "volume": [10.0, 0.0, 5.0, 5.0, 5.0],  # 第 2 列 zero_volume
        },
        index=index,
    )

    outcome = CandleSanitationService().sanitize(CandleSeries(INSTRUMENT, candles))
    counts = outcome.counts_by_flag()

    assert len(outcome.accepted) == 4
    assert outcome.rejected_bar_count == 1
    assert counts["ohlc_invalid"] == 1
    assert counts["zero_volume"] == 1
    assert counts["price_jump"] == 1
    assert counts["negative_value"] == 0
    # 輸入沒有被改到
    assert len(candles) == 5


def test_sanitation_threshold_depends_on_timeframe():
    service = CandleSanitationService()
    assert service.maximum_absolute_return("1m") < service.maximum_absolute_return("1d")
    with pytest.raises(ValueError):
        service.maximum_absolute_return("3m")
