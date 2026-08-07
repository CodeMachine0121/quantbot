# quantbot/entrypoints/backfill_trades_command.py
"""回補一段歷史逐筆成交，入庫並跟官方 K 線對帳。

    uv run python -m quantbot.entrypoints.backfill_trades_command \
        --symbol BTC/USDT --market spot --start 2026-07-15 --end 2026-07-16

一天的 BTC/USDT 現貨 aggTrades 是七十幾萬列，所以區間 NEVER 一次給一個月：
那是三十個日檔、兩千多萬列，而通常沒有人需要那麼多。
"""

from __future__ import annotations

import argparse
import asyncio

import httpx
import pandas as pd

from quantbot.application.backfill_trades_application import BackfillTradesApplication
from quantbot.config import settings
from quantbot.domain.services.candle_agreement_service import CandleAgreementService
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.binance.binance_agg_trade_csv_parser import (
    BinanceAggTradeCsvParser,
)
from quantbot.infrastructure.binance.binance_archive_candle_source import (
    BinanceArchiveCandleSource,
)
from quantbot.infrastructure.binance.binance_archive_downloader import (
    BinanceArchiveDownloader,
)
from quantbot.infrastructure.binance.binance_archive_trade_source import (
    BinanceArchiveTradeSource,
)
from quantbot.infrastructure.binance.binance_archive_url_builder import (
    BinanceArchiveUrlBuilder,
)
from quantbot.infrastructure.binance.binance_candle_csv_parser import (
    BinanceCandleCsvParser,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_trade_repository import (
    TimescaleTradeRepository,
)
from quantbot.infrastructure.reporting.text_trade_ingest_report_renderer import (
    TextTradeIngestReportRenderer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    return parser.parse_args()


async def main() -> int:
    arguments = parse_arguments()
    listing = Listing(symbol=arguments.symbol, market=Market(arguments.market))
    period = TimeRange(
        pd.Timestamp(arguments.start, tz="UTC"), pd.Timestamp(arguments.end, tz="UTC")
    )

    database = PostgresDatabase.from_settings()
    url_builder = BinanceArchiveUrlBuilder()
    # 一天的 zip 是 11 MB，逐檔驗 checksum，所以 timeout 給得比 K 線那條寬
    async with httpx.AsyncClient(timeout=180.0) as client:
        downloader = BinanceArchiveDownloader(
            client, url_builder, cache_directory=settings.raw_data_directory
        )
        application = BackfillTradesApplication(
            trades=BinanceArchiveTradeSource(
                downloader, url_builder, BinanceAggTradeCsvParser()
            ),
            repository=TimescaleTradeRepository(database),
            candles=BinanceArchiveCandleSource(
                downloader, url_builder, BinanceCandleCsvParser()
            ),
            agreement=CandleAgreementService(),
            reconciliation_timeframe=Timeframe("1m"),
        )
        try:
            report = await application.run(listing, period)
        finally:
            await database.close()

    print(TextTradeIngestReportRenderer().render(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
