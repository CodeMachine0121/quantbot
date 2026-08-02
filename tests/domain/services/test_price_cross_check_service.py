# tests/domain/services/test_price_cross_check_service.py
import pandas as pd
import pytest

from quantbot.domain.services.price_cross_check_service import PriceCrossCheckService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
NOW = pd.Timestamp("2026-09-22 04:00", tz="UTC")


def test_cross_check_flags_only_the_days_over_tolerance():
    index = pd.date_range("2026-01-01", periods=2, freq="1D", tz="UTC")
    ours = pd.Series([100.0, 101.0], index=index)
    theirs = pd.Series([100.2, 130.0], index=index)

    report = PriceCrossCheckService(tolerance=0.01).compare(
        ours, theirs, reference_name="coingecko"
    )

    assert not report.passed
    assert len(report.flagged_days) == 1
    assert report.maximum_relative_difference == pytest.approx(0.2231, abs=1e-4)
    assert report.reference_name == "coingecko"
