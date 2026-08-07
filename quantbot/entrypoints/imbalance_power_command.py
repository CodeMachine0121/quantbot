# quantbot/entrypoints/imbalance_power_command.py
"""算 OBI 並驗證它對未來報酬有沒有資訊。

    uv run python -m quantbot.entrypoints.imbalance_power_command \
        --symbol BTC/USDT --market spot --timeframe 1m \
        --start 2026-08-04T16:50 --end 2026-08-04T18:00

資料要先錄過（Day 09 的 record_microstructure_command），因為現貨的掛單簿歷史
在免費資料源裡沒有——手上只會有自己錄下來的那幾段。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.evaluate_imbalance_power_application import (
    EvaluateImbalancePowerApplication,
)
from quantbot.domain.features.order_book_imbalance import OrderBookImbalance
from quantbot.domain.services.predictive_power_service import PredictivePowerService
from quantbot.domain.values.depth_aggregation import DepthAggregation
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_imbalance_power_chart_renderer import (
    PlotlyImbalancePowerChartRenderer,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)
from quantbot.infrastructure.persistence.timescale_depth_repository import (
    TimescaleDepthRepository,
)
from quantbot.infrastructure.reporting.text_imbalance_power_report_renderer import (
    TextImbalancePowerReportRenderer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--buckets", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("notebooks"))
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
    # 三個深度各一個特徵。錄下來的深度就這三種，所以清單從 DepthColumns 來，
    # NEVER 在這裡另外寫一份 (5, 10, 20)。
    features = [
        OrderBookImbalance(level, aggregation=DepthAggregation.MEAN)
        for level in DepthColumns.LEVELS
    ]

    database = PostgresDatabase.from_settings()
    depth_repository = TimescaleDepthRepository(database)
    application = EvaluateImbalancePowerApplication(
        candles=TimescaleCandleRepository(database),
        depth=depth_repository,
        power=PredictivePowerService(bucket_count=arguments.buckets),
    )
    try:
        report = await application.run(instrument, period, features=features)
        depth = await depth_repository.read(Listing.of(instrument), period)
    finally:
        await database.close()

    print(TextImbalancePowerReportRenderer().render(report))

    # 圖只畫最淺的那個深度（前 5 檔）：三個深度疊在一張圖上會互相蓋掉，
    # 而三者的差異在上面那張表裡已經是逐列可比的了。
    shallowest = features[0]
    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day10-{instrument.storage_key}-obi.html"
    PlotlyImbalancePowerChartRenderer(shallowest).render(
        depth,
        [
            candidate
            for candidate in report.native_reports
            if candidate.feature_name == f"obi_{shallowest.depth_level}"
        ],
    ).write_html(chart_path)
    print(f"\n圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
