# quantbot/application/ingest_pipeline_application.py
from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pandas as pd

from quantbot.domain.dto.data_integrity_report import DataIntegrityReportDto
from quantbot.domain.dto.pipeline_report import InstrumentReportDto, PipelineReportDto
from quantbot.domain.dto.price_cross_check_report import PriceCrossCheckReportDto
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.clock import Clock
from quantbot.domain.interfaces.reference_price_source import ReferencePriceSource
from quantbot.domain.services.candle_sanitation_service import CandleSanitationService
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.price_cross_check_service import PriceCrossCheckService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.pipeline_configuration import PipelineConfiguration
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange


class IngestPipelineApplication:
    """六個步驟的編排：盤點 → 路由 → 取得 → 清洗 → 入庫 → 複驗。

    它自己不查缺口、不決定路由、不清洗、不寫資料庫、不打任何 HTTP——那幾件事
    各有主人。它負責的是順序、併發，以及把每一段的結果收進報告。

    建構參數全部是介面或 domain service，所以測試時只要對最外層的介面做替身。
    """

    def __init__(
        self,
        configuration: PipelineConfiguration,
        *,
        sources: Mapping[SourceKind, CandleSource],
        repository: CandleRepository,
        reference: ReferencePriceSource,
        routing: SourceRoutingService,
        integrity: DataIntegrityService,
        sanitation: CandleSanitationService,
        cross_check: PriceCrossCheckService,
        clock: Clock,
    ) -> None:
        self._configuration = configuration
        self._sources = sources
        self._repository = repository
        self._reference = reference
        self._routing = routing
        self._integrity = integrity
        self._sanitation = sanitation
        self._cross_check = cross_check
        self._clock = clock
        self._semaphore = asyncio.Semaphore(configuration.maximum_concurrency)

    async def run(self) -> PipelineReportDto:
        now = self._clock.now()
        reports = await asyncio.gather(
            *(
                self._synchronize(instrument, now=now)
                for instrument in self._configuration.instruments
            ),
            # 單一 instrument 失敗不拖垮整批，但失敗本身要進報告
            return_exceptions=True,
        )
        return PipelineReportDto(
            run_at=now,
            instrument_reports=tuple(
                self._as_report(instrument, outcome)
                for instrument, outcome in zip(
                    self._configuration.instruments, reports, strict=True
                )
            ),
        )

    async def _synchronize(
        self, instrument: Instrument, *, now: pd.Timestamp
    ) -> InstrumentReportDto:
        async with self._semaphore:
            report = InstrumentReportDto(instrument=instrument)
            # 右端一律往下取整到整根 K 線，排除還沒收完的那一根
            period = TimeRange(
                self._configuration.history_start, instrument.timeframe.floor(now)
            )

            # [1] 盤點
            report.integrity_before = await self._inspect(instrument, period)

            # [2][3][4][5] 每段缺口：路由 → 取得 → 清洗 → 入庫
            for gap in report.integrity_before.gaps:
                gap_period = TimeRange(gap.start, gap.end + instrument.timeframe.step)
                for instruction in self._routing.route(gap_period, now=now):
                    fetched = await self._sources[instruction.source_kind].load(
                        instrument, instruction.period
                    )
                    outcome = self._sanitation.sanitize(fetched)
                    self._accumulate_anomalies(report, outcome.counts_by_flag())
                    written = await self._repository.save(
                        outcome.accepted, source=str(instruction.source_kind)
                    )
                    report.written_bar_counts[str(instruction.source_kind)] = (
                        report.written_bar_counts.get(str(instruction.source_kind), 0)
                        + written
                    )

            # [6] 複驗：同一個 DataIntegrityService 再跑一次，缺口應該是空的
            report.integrity_after = await self._inspect(instrument, period)
            report.cross_check = await self._verify_against_reference(
                instrument, now=now
            )
            return report

    async def _inspect(
        self, instrument: Instrument, period: TimeRange
    ) -> DataIntegrityReportDto:
        open_times = await self._repository.existing_open_times(instrument, period)
        return self._integrity.inspect(
            open_times, period=period, timeframe=instrument.timeframe
        )

    async def _verify_against_reference(
        self, instrument: Instrument, *, now: pd.Timestamp
    ) -> PriceCrossCheckReportDto | None:
        if not self._reference.supports(instrument.symbol):
            return None  # 沒有對照來源就留空，NEVER 默默當成通過

        window = TimeRange(
            now - pd.Timedelta(days=self._configuration.cross_check_sample_days), now
        )
        theirs = await self._reference.daily_close(instrument.symbol, window)
        ours = await self._repository.read(instrument, window)
        return self._cross_check.compare(
            ours.frame["close"].resample("1D").last().rename("ours"),
            theirs,
            reference_name=self._reference.name,
        )

    @staticmethod
    def _accumulate_anomalies(
        report: InstrumentReportDto, counts: Mapping[str, int]
    ) -> None:
        for flag, count in counts.items():
            report.anomaly_counts[flag] = report.anomaly_counts.get(flag, 0) + count

    @staticmethod
    def _as_report(
        instrument: Instrument, outcome: InstrumentReportDto | BaseException
    ) -> InstrumentReportDto:
        if isinstance(outcome, BaseException):
            return InstrumentReportDto(
                instrument=instrument, failure=f"{type(outcome).__name__}: {outcome}"
            )
        return outcome
