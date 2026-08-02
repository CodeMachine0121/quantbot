# quantbot/application/backfill_candles_application.py
from __future__ import annotations

from collections.abc import Mapping

from quantbot.domain.dto.data_integrity_report import DataIntegrityReportDto
from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.clock import Clock
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange


class BackfillCandlesApplication:
    """回補一段 K 線：路由 → 依路由向各來源取得 → 合併 → 檢查完整性。

    它只認 CandleSource 這個介面。哪一條是批次 zip、哪一條是 REST，是組裝根
    的決定；這裡連 Binance 這個字都不會出現，換交易所不必改這個檔案。
    """

    def __init__(
        self,
        *,
        sources: Mapping[SourceKind, CandleSource],
        routing: SourceRoutingService,
        integrity: DataIntegrityService,
        clock: Clock,
    ) -> None:
        self._sources = sources
        self._routing = routing
        self._integrity = integrity
        self._clock = clock

    async def run(self, instrument: Instrument, period: TimeRange) -> CandleSeries:
        now = self._clock.now()
        # 右端收到最後一根已收盤的 K 線。TimeRange 是半開區間，
        # 所以拿當下那根還在跳動的 K 線的開盤時間當 end 剛好排除它。
        bounded = period.clamp_end(instrument.timeframe.floor(now))

        series = CandleSeries.empty(instrument)
        for instruction in self._routing.route(bounded, now=now):
            fetched = await self._sources[instruction.source_kind].load(
                instrument, instruction.period
            )
            # 批次檔是定稿、REST 是暫時的。route() 保證批次段先來，
            # 而 merge 以呼叫者為準，所以重疊時批次勝出。
            series = series.merge(fetched)

        return series.restricted_to(bounded)

    async def inspect(
        self, series: CandleSeries, period: TimeRange
    ) -> DataIntegrityReportDto:
        """回補完的完整性報告。用的是全專案同一個缺漏偵測。"""
        return self._integrity.inspect(
            series.open_times, period=period, timeframe=series.instrument.timeframe
        )
