# quantbot/entrypoints/backfill_command.py
"""回補一段 K 線並存成 parquet。

    uv run python -m quantbot.entrypoints.backfill_command \
        --symbol BTC/USDT --market spot --timeframe 1m \
        --start 2025-01-01 --end 2026-09-16 --out data/klines
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import ccxt.async_support as ccxt
import httpx
import pandas as pd

from quantbot.application.backfill_candles_application import BackfillCandlesApplication
from quantbot.config import settings
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.binance.binance_archive_candle_source import (
    BinanceArchiveCandleSource,
)
from quantbot.infrastructure.binance.binance_archive_downloader import (
    BinanceArchiveDownloader,
)
from quantbot.infrastructure.binance.binance_archive_url_builder import (
    BinanceArchiveUrlBuilder,
)
from quantbot.infrastructure.binance.binance_candle_csv_parser import (
    BinanceCandleCsvParser,
)
from quantbot.infrastructure.binance.binance_rate_limit_guard import (
    BinanceRateLimitGuard,
)
from quantbot.infrastructure.binance.binance_rest_candle_source import (
    BinanceRestCandleSource,
)
from quantbot.infrastructure.system_clock import SystemClock


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=Path, default=Path("data/klines"))
    return parser.parse_args()


async def main() -> int:
    arguments = parse_arguments()
    instrument = Instrument(
        symbol=arguments.symbol,
        market=Market(arguments.market),
        timeframe=Timeframe(arguments.timeframe),
    )
    period = TimeRange(
        pd.Timestamp(arguments.start, tz="UTC"), pd.Timestamp(arguments.end, tz="UTC")
    )

    # 這裡是組裝根：全專案唯一知道所有具體型別的地方。
    # 上面的 application 只認 CandleSource，所以要換掉任何一條來源，改的是這幾行。
    url_builder = BinanceArchiveUrlBuilder()
    exchange = ccxt.binance({"enableRateLimit": True})
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            application = BackfillCandlesApplication(
                sources={
                    SourceKind.ARCHIVE: BinanceArchiveCandleSource(
                        BinanceArchiveDownloader(
                            client,
                            url_builder,
                            cache_directory=settings.raw_data_directory,
                        ),
                        url_builder,
                        BinanceCandleCsvParser(),
                    ),
                    SourceKind.REST: BinanceRestCandleSource(
                        exchange, BinanceRateLimitGuard()
                    ),
                },
                routing=SourceRoutingService(),
                integrity=DataIntegrityService(),
                clock=SystemClock(),
            )
            series = await application.run(instrument, period)
            integrity = await application.inspect(series, period)
        finally:
            await exchange.close()

    arguments.out.mkdir(parents=True, exist_ok=True)
    series.with_identity_columns().to_parquet(
        arguments.out / f"{instrument.storage_key}.parquet"
    )
    integrity.to_frame().to_csv(
        arguments.out / f"{instrument.storage_key}_gaps.csv", index=False
    )

    print(
        f"{len(series)} 根，缺 {integrity.missing_bar_count} 根，"
        f"覆蓋率 {integrity.coverage_ratio:.4%}"
    )
    return 0 if integrity.is_complete else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
