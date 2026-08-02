# tests/domain/services/test_data_integrity_service.py
import pandas as pd
import pytest

from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
NOW = pd.Timestamp("2026-09-22 04:00", tz="UTC")


def test_integrity_groups_consecutive_missing_bars():
    period = TimeRange(
        pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-01-01 00:20", tz="UTC")
    )
    timeframe = Timeframe("1m")
    expected = timeframe.expected_open_times(period)
    actual = expected.delete([3, 4, 5, 11])

    report = DataIntegrityService().inspect(actual, period=period, timeframe=timeframe)

    assert report.expected_bar_count == 20
    assert report.actual_bar_count == 16
    assert report.missing_bar_count == 4
    assert [gap.bar_count for gap in report.gaps] == [3, 1]
    assert report.gaps[0].start == expected[3]
    assert not report.is_complete
    assert report.coverage_ratio == pytest.approx(0.8)


def test_integrity_reports_complete_when_nothing_is_missing():
    period = TimeRange(
        pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-01-01 00:10", tz="UTC")
    )
    timeframe = Timeframe("1m")
    report = DataIntegrityService().inspect(
        timeframe.expected_open_times(period), period=period, timeframe=timeframe
    )

    assert report.is_complete and report.missing_bar_count == 0
    assert report.to_frame().empty
