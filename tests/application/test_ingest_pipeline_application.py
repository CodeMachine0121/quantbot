# tests/application/test_ingest_pipeline_application.py
"""管線的測試：注入真實的 domain service，只對最外層的 Protocol 做替身。

替身一律用 create_autospec(..., spec_set=True)——簽章會被檢查，所以 Protocol
改了方法名或參數，這裡會紅。NEVER 手寫 fake 類別。
"""

from unittest.mock import create_autospec

import pandas as pd
import pytest

from quantbot.application.ingest_pipeline_application import IngestPipelineApplication
from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.clock import Clock
from quantbot.domain.interfaces.reference_price_source import ReferencePriceSource
from quantbot.domain.services.candle_sanitation_service import CandleSanitationService
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.price_cross_check_service import PriceCrossCheckService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.pipeline_configuration import PipelineConfiguration
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe

NOW = pd.Timestamp("2026-09-22 04:30", tz="UTC")
HISTORY_START = pd.Timestamp("2026-09-22 00:00", tz="UTC")
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def complete_open_times() -> pd.DatetimeIndex:
    """這段期間「應該」有的每一根開盤時間。"""
    timeframe = INSTRUMENT.timeframe
    return timeframe.expected_open_times(TimeRange(HISTORY_START, timeframe.floor(NOW)))


def make_candles(start: str, bar_count: int, *, close: float = 100.0) -> CandleSeries:
    index = pd.date_range(
        start, periods=bar_count, freq="1h", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1.0,
            },
            index=index,
        ),
    )


def build_pipeline(*, existing: pd.DatetimeIndex, fetched: CandleSeries):
    repository = create_autospec(CandleRepository, spec_set=True, instance=True)
    # 盤點時回傳既有的開盤時間，複驗時回傳「補完之後」的完整時間軸
    repository.existing_open_times.side_effect = [
        existing,
        complete_open_times(),
    ]
    repository.save.return_value = len(fetched)

    source = create_autospec(CandleSource, spec_set=True, instance=True)
    source.load.return_value = fetched

    reference = create_autospec(ReferencePriceSource, spec_set=True, instance=True)
    reference.supports.return_value = False

    clock = create_autospec(Clock, spec_set=True, instance=True)
    clock.now.return_value = NOW

    application = IngestPipelineApplication(
        PipelineConfiguration(instruments=(INSTRUMENT,), history_start=HISTORY_START),
        sources={SourceKind.ARCHIVE: source, SourceKind.REST: source},
        repository=repository,
        reference=reference,
        routing=SourceRoutingService(),
        integrity=DataIntegrityService(),
        sanitation=CandleSanitationService(),
        cross_check=PriceCrossCheckService(),
        clock=clock,
    )
    return application, repository, source, reference


@pytest.mark.asyncio
async def test_gaps_are_fetched_and_written_then_reverified():
    existing = complete_open_times().delete([1, 2])  # 少了兩根
    application, repository, source, _ = build_pipeline(
        existing=existing, fetched=make_candles("2026-09-22 01:00", 2)
    )

    report = await application.run()
    instrument_report = report.instrument_reports[0]

    assert instrument_report.integrity_before.missing_bar_count == 2
    assert instrument_report.integrity_after.is_complete
    assert sum(instrument_report.written_bar_counts.values()) == 2
    source.load.assert_awaited_once()
    repository.save.assert_awaited_once()
    assert instrument_report.ok and report.ok


@pytest.mark.asyncio
async def test_nothing_is_fetched_when_there_is_no_gap():
    application, repository, source, _ = build_pipeline(
        existing=complete_open_times(), fetched=CandleSeries.empty(INSTRUMENT)
    )

    report = await application.run()

    source.load.assert_not_awaited()
    repository.save.assert_not_awaited()
    assert report.instrument_reports[0].written_bar_counts == {}
    assert report.ok


@pytest.mark.asyncio
async def test_a_failing_instrument_does_not_take_down_the_batch():
    application, repository, _, _ = build_pipeline(
        existing=pd.DatetimeIndex([], tz="UTC"),
        fetched=CandleSeries.empty(INSTRUMENT),
    )
    repository.existing_open_times.side_effect = RuntimeError("連線掛了")

    report = await application.run()

    assert not report.ok
    assert "連線掛了" in report.instrument_reports[0].failure
