# quantbot/entrypoints/vwap_command.py
"""算 VWAP 與偏離度，統計價格待在通道內外的比例，輸出互動圖。

    uv run python -m quantbot.entrypoints.vwap_command \
        --symbol BTC/USDT --market spot --timeframe 1m \
        --start 2026-07-15 --end 2026-07-16
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.domain.features.volume_weighted_average_price import VWAP
from quantbot.domain.features.vwap_deviation import VWAPDeviation
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.price_source import PriceSource
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.vwap_mode import VWAPMode
from quantbot.infrastructure.charting.plotly_vwap_chart_renderer import (
    PlotlyVWAPChartRenderer,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--mode", default=VWAPMode.SESSION.value, choices=[m.value for m in VWAPMode]
    )
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("notebooks"))
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    """1m 走原始表，其餘走 Day 07 的 continuous aggregate。"""
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

    database = PostgresDatabase.from_settings()
    repository = TimescaleCandleRepository(database, table=table_for(timeframe))
    try:
        view = MarketView(candles=await repository.read(instrument, period))
    finally:
        await database.close()

    feature = VWAP(
        mode=VWAPMode(arguments.mode),
        window=arguments.window,
        price_source=PriceSource.TYPICAL,
    )
    line = feature.compute(view)
    deviation = VWAPDeviation(feature).compute(view)
    price = feature.price_source.of(view.candles.frame)
    valid = deviation.dropna()

    print(
        f"{len(view.candles):,} 根 K 線：{view.candles.open_times[0]} → "
        f"{view.candles.open_times[-1]}"
    )
    print(f"{feature.name}：最後一根 {line.iloc[-1]:,.2f}，價格 {price.iloc[-1]:,.2f}")
    print(f"價格在 VWAP 之上的比例：{(price > line).mean():.2%}")
    for multiplier in (1.0, 2.0):
        outside = valid.abs() > multiplier
        print(
            f"偏離超過 {multiplier:.0f} 個標準差：{int(outside.sum()):,} 根"
            f"（{outside.mean():.2%}）"
        )

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day11-{instrument.storage_key}-{feature.name}.html"
    PlotlyVWAPChartRenderer(feature).render(view).write_html(chart_path)
    print(f"圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
