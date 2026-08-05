# quantbot/entrypoints/breakout_command.py
"""統計真假突破，並輸出把突破標在 K 線上的互動圖。

    uv run python -m quantbot.entrypoints.breakout_command \
        --symbol BTC/USDT --market spot --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01 --window 20 --horizon 10
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.analyze_breakouts_application import (
    AnalyzeBreakoutsApplication,
)
from quantbot.domain.features.breakout import Breakout
from quantbot.domain.services.breakout_labelling_service import (
    BreakoutLabellingService,
)
from quantbot.domain.services.breakout_statistics_service import (
    BreakoutStatisticsService,
)
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_breakout_chart_renderer import (
    PlotlyBreakoutChartRenderer,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)
from quantbot.infrastructure.reporting.text_breakout_statistics_report_renderer import (
    TextBreakoutStatisticsReportRenderer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("notebooks"))
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


async def main() -> int:
    arguments = parse_arguments()
    timeframe = Timeframe(arguments.timeframe)
    instrument = Instrument(
        symbol=arguments.symbol,
        market=Market(arguments.market),
        timeframe=timeframe,
    )
    period = TimeRange(
        pd.Timestamp(arguments.start, tz="UTC"), pd.Timestamp(arguments.end, tz="UTC")
    )
    labelling = BreakoutLabellingService(horizon=arguments.horizon)

    database = PostgresDatabase.from_settings()
    repository = TimescaleCandleRepository(database, table=table_for(timeframe))
    application = AnalyzeBreakoutsApplication(
        candles=repository,
        labelling=labelling,
        statistics=BreakoutStatisticsService(),
    )
    try:
        reports = {
            side: await application.run(
                instrument,
                period,
                breakout=Breakout(side=side, window=arguments.window),
            )
            for side in ExtremeSide
        }
        view = MarketView(candles=await repository.read(instrument, period))
    finally:
        await database.close()

    renderer = TextBreakoutStatisticsReportRenderer()
    print(f"{instrument.storage_key}，前 {arguments.window} 根極值")
    for side, report in reports.items():
        print(f"\n[{'突破前高' if side is ExtremeSide.HIGH else '跌破前低'}]")
        print(renderer.render(report))

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day13-{instrument.storage_key}-breakout.html"
    PlotlyBreakoutChartRenderer(
        breakout=Breakout(side=ExtremeSide.HIGH, window=arguments.window),
        labelling=labelling,
    ).render(view).write_html(chart_path)
    print(f"\n圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
