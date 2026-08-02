# tests/application/test_backfill_candles_application.py
"""Application 的測試：注入真實的 domain service，只對最外層的 Protocol 做替身。

替身一律用 create_autospec(..., spec_set=True)——簽章會被檢查，
所以 Protocol 改了方法名或參數，這裡會紅。NEVER 手寫 fake 類別。
"""

from unittest.mock import create_autospec

import pandas as pd
import pytest

from quantbot.application.backfill_candles_application import BackfillCandlesApplication
from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.clock import Clock
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)
NOW = pd.Timestamp("2026-09-22 04:30", tz="UTC")


def candles_between(start: str, bar_count: int) -> CandleSeries:
    index = pd.date_range(
        start, periods=bar_count, freq="1h", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0},
            index=index,
        ),
    )


def make_source(series: CandleSeries):
    source = create_autospec(CandleSource, spec_set=True, instance=True)
    source.load.return_value = series
    return source


def make_clock(now: pd.Timestamp = NOW):
    clock = create_autospec(Clock, spec_set=True, instance=True)
    clock.now.return_value = now
    return clock


def build_application(sources):
    return BackfillCandlesApplication(
        sources=sources,
        routing=SourceRoutingService(),
        integrity=DataIntegrityService(),
        clock=make_clock(),
    )


@pytest.mark.asyncio
async def test_long_period_uses_both_sources_and_archive_wins_on_overlap():
    archive = candles_between("2026-09-19 00:00", 48)
    rest = CandleSeries(
        INSTRUMENT, candles_between("2026-09-19 00:00", 60).frame.assign(close=-1.0)
    )
    archive_source, rest_source = make_source(archive), make_source(rest)

    application = build_application(
        {SourceKind.ARCHIVE: archive_source, SourceKind.REST: rest_source}
    )
    series = await application.run(
        INSTRUMENT,
        TimeRange(
            pd.Timestamp("2026-09-01", tz="UTC"), pd.Timestamp("2026-09-23", tz="UTC")
        ),
    )

    archive_source.load.assert_awaited_once()
    rest_source.load.assert_awaited_once()
    # 重疊的那 48 根以批次為準
    overlapping = series.frame.loc[archive.open_times, "close"]
    assert (overlapping == 1.5).all()


@pytest.mark.asyncio
async def test_the_bar_in_progress_is_never_returned():
    application = build_application(
        {SourceKind.REST: make_source(candles_between("2026-09-22 00:00", 6))}
    )
    series = await application.run(
        INSTRUMENT,
        TimeRange(
            pd.Timestamp("2026-09-22 00:00", tz="UTC"), NOW + pd.Timedelta(hours=2)
        ),
    )

    # NOW 是 04:30，04:00 那根還在跳動，所以最後一根是 03:00
    assert series.open_times[-1] == pd.Timestamp("2026-09-22 03:00", tz="UTC")


@pytest.mark.asyncio
async def test_short_recent_gap_never_touches_the_archive():
    archive_source = make_source(CandleSeries.empty(INSTRUMENT))
    rest_source = make_source(candles_between("2026-09-22 01:00", 2))

    application = build_application(
        {SourceKind.ARCHIVE: archive_source, SourceKind.REST: rest_source}
    )
    await application.run(
        INSTRUMENT,
        TimeRange(
            pd.Timestamp("2026-09-22 01:00", tz="UTC"),
            pd.Timestamp("2026-09-22 03:00", tz="UTC"),
        ),
    )

    archive_source.load.assert_not_awaited()
    rest_source.load.assert_awaited_once()


@pytest.mark.asyncio
async def test_integrity_report_comes_from_the_same_service_the_pipeline_uses():
    series = candles_between("2026-09-20 00:00", 24)
    application = build_application({SourceKind.REST: make_source(series)})
    period = TimeRange(
        pd.Timestamp("2026-09-20 00:00", tz="UTC"),
        pd.Timestamp("2026-09-21 00:00", tz="UTC"),
    )

    report = await application.inspect(series, period)
    assert report.is_complete and report.expected_bar_count == 24
