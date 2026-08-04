# quantbot/application/backfill_trades_application.py
from __future__ import annotations

from typing import ClassVar

from quantbot.domain.dto.trade_ingest_report import TradeIngestReportDto
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.trade_repository import TradeRepository
from quantbot.domain.interfaces.trade_source import TradeSource
from quantbot.domain.services.candle_agreement_service import CandleAgreementService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe


class BackfillTradesApplication:
    """把一段歷史逐筆成交補進資料庫，並用官方 K 線對帳。

    四個步驟：取得 → 查斷號 → 入庫 → 重建 K 線跟官方比。第四步不是可選的裝飾，
    它是這條路徑上唯一的正確性把關——逐筆成交沒有免費的第二個來源可以比對，
    但它聚合起來必須等於官方的 K 線，而那份 K 線我們早在 Day 03 就有辦法拿到。
    """

    DEFAULT_RECONCILIATION_TIMEFRAME: ClassVar[Timeframe] = Timeframe("1m")

    def __init__(
        self,
        *,
        trades: TradeSource,
        repository: TradeRepository,
        candles: CandleSource,
        agreement: CandleAgreementService,
        reconciliation_timeframe: Timeframe | None = None,
    ) -> None:
        self._trades = trades
        self._repository = repository
        self._candles = candles
        self._agreement = agreement
        self._reconciliation_timeframe = (
            reconciliation_timeframe or self.DEFAULT_RECONCILIATION_TIMEFRAME
        )

    async def run(self, listing: Listing, period: TimeRange) -> TradeIngestReportDto:
        fetched = await self._trades.load(listing, period)
        if fetched.is_empty():
            return TradeIngestReportDto(
                listing=listing,
                fetched_row_count=0,
                written_row_count=0,
                missing_trade_id_count=0,
            )

        written = await self._repository.save(fetched, source="binance_archive")

        rebuilt = fetched.aggregate_to_candles(self._reconciliation_timeframe)
        official = await self._candles.load(
            Instrument(
                symbol=listing.symbol,
                market=listing.market,
                timeframe=self._reconciliation_timeframe,
            ),
            period,
        )

        return TradeIngestReportDto(
            listing=listing,
            fetched_row_count=len(fetched),
            written_row_count=written,
            missing_trade_id_count=fetched.missing_trade_id_count(),
            agreement=self._agreement.compare(rebuilt, official),
        )
