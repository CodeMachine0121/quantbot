# quantbot/entrypoints/record_microstructure_command.py
"""錄一段即時的成交與掛單簿。

    uv run python -m quantbot.entrypoints.record_microstructure_command \
        --symbol BTC/USDT --market spot --seconds 120

不給 --seconds 就一直錄下去（正式部署的用法）。錄之前要先跑過 migrate，
order_book_depth 與 agg_trades 兩張表都要存在。
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from quantbot.application.record_microstructure_application import (
    RecordMicrostructureApplication,
)
from quantbot.domain.services.order_book_sequence_service import (
    OrderBookSequenceService,
)
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.recording_configuration import RecordingConfiguration
from quantbot.infrastructure.binance.binance_rest_order_book_snapshot_source import (
    BinanceRestOrderBookSnapshotSource,
)
from quantbot.infrastructure.binance.binance_snapshot_rate_guard import (
    BinanceSnapshotRateGuard,
)
from quantbot.infrastructure.binance.binance_stream_payload_parser import (
    BinanceStreamPayloadParser,
)
from quantbot.infrastructure.binance.binance_stream_url_builder import (
    BinanceStreamUrlBuilder,
)
from quantbot.infrastructure.binance.binance_websocket_message_source import (
    BinanceWebsocketMessageSource,
)
from quantbot.infrastructure.binance.binance_websocket_order_book_stream import (
    BinanceWebsocketOrderBookStream,
)
from quantbot.infrastructure.binance.binance_websocket_trade_stream import (
    BinanceWebsocketTradeStream,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_depth_repository import (
    TimescaleDepthRepository,
)
from quantbot.infrastructure.persistence.timescale_trade_repository import (
    TimescaleTradeRepository,
)
from quantbot.infrastructure.system_clock import SystemClock


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--capture-interval", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=None)
    return parser.parse_args()


async def main() -> int:
    arguments = parse_arguments()
    listing = Listing(symbol=arguments.symbol, market=Market(arguments.market))
    configuration = RecordingConfiguration(
        listing=listing,
        snapshot_depth=arguments.depth,
        capture_interval_seconds=arguments.capture_interval,
        duration_seconds=arguments.seconds,
    )

    clock = SystemClock()
    parser = BinanceStreamPayloadParser()
    url_builder = BinanceStreamUrlBuilder()
    # 兩個 stream 一條連線。順序不影響訂閱結果，但兩支 stream 類別都要用同一個
    # tuple，否則它們會各自開一條連線，斷線時就不再同進同出。
    streams = (parser.AGG_TRADE_STREAM, parser.DEPTH_STREAM)
    messages = BinanceWebsocketMessageSource(url_builder)

    database = PostgresDatabase.from_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        application = RecordMicrostructureApplication(
            configuration,
            trades=BinanceWebsocketTradeStream(messages, parser, streams=streams),
            order_book=BinanceWebsocketOrderBookStream(
                messages, parser, streams=streams
            ),
            snapshots=BinanceRestOrderBookSnapshotSource(
                client, url_builder, parser, BinanceSnapshotRateGuard(clock)
            ),
            trade_repository=TimescaleTradeRepository(database),
            depth_repository=TimescaleDepthRepository(database),
            sequence=OrderBookSequenceService(),
            clock=clock,
        )
        try:
            report = await application.run()
        finally:
            await database.close()

    print(f"{report.listing.storage_key}")
    print(f"  成交寫入 {report.recorded_trade_count:,} 列")
    print(f"  深度摘要寫入 {report.recorded_depth_row_count:,} 列")
    print(
        f"  掛單簿更新：套用 {report.applied_update_count:,}、"
        f"丟棄 {report.discarded_update_count:,}、"
        f"重取快照 {report.resynchronization_count:,} 次"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
