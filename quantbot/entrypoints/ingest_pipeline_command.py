# quantbot/entrypoints/ingest_pipeline_command.py
"""把設定檔裡所有交易對補到最新，並輸出一份資料完整性報告。

uv run python -m quantbot.entrypoints.ingest_pipeline_command
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import ccxt.async_support as ccxt
import httpx

from quantbot.application.ingest_pipeline_application import IngestPipelineApplication
from quantbot.config import settings
from quantbot.domain.services.candle_sanitation_service import CandleSanitationService
from quantbot.domain.services.data_integrity_service import DataIntegrityService
from quantbot.domain.services.price_cross_check_service import PriceCrossCheckService
from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.source_kind import SourceKind
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
from quantbot.infrastructure.coingecko.coingecko_reference_price_source import (
    CoinGeckoReferencePriceSource,
)
from quantbot.infrastructure.configuration.yaml_pipeline_configuration_loader import (
    YamlPipelineConfigurationLoader,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)
from quantbot.infrastructure.reporting.text_pipeline_report_renderer import (
    TextPipelineReportRenderer,
)
from quantbot.infrastructure.system_clock import SystemClock

CONFIGURATION_PATH = Path("quantbot/infrastructure/configuration/pipeline.yaml")


async def main() -> int:
    configuration = YamlPipelineConfigurationLoader().load(CONFIGURATION_PATH)
    database = PostgresDatabase.from_settings()
    url_builder = BinanceArchiveUrlBuilder()
    exchange = ccxt.binance({"enableRateLimit": True})

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            application = IngestPipelineApplication(
                configuration,
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
                repository=TimescaleCandleRepository(database),
                reference=CoinGeckoReferencePriceSource(
                    client, api_key=settings.coingecko_api_key
                ),
                routing=SourceRoutingService(),
                integrity=DataIntegrityService(),
                sanitation=CandleSanitationService(),
                cross_check=PriceCrossCheckService(
                    tolerance=configuration.cross_check_tolerance
                ),
                clock=SystemClock(),
            )
            report = await application.run()
        finally:
            await exchange.close()
            await database.close()

    print(TextPipelineReportRenderer().render(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
