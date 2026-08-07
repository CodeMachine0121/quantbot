# quantbot/entrypoints/activity_command.py
"""算交易活躍度與 ATR，印出時段節奏，輸出熱力圖。

    uv run python -m quantbot.entrypoints.activity_command \
        --symbol BTC/USDT --market spot --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.domain.features.average_true_range import ATR
from quantbot.domain.features.trading_activity import TradingActivity
from quantbot.domain.values.activity_baseline import ActivityBaseline
from quantbot.domain.values.activity_measure import ActivityMeasure
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_activity_heatmap_renderer import (
    PlotlyActivityHeatmapRenderer,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--window", type=int, default=168)
    parser.add_argument("--atr-period", type=int, default=14)
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

    database = PostgresDatabase.from_settings()
    try:
        view = MarketView(
            candles=await TimescaleCandleRepository(
                database, table=table_for(timeframe)
            ).read(instrument, period)
        )
    finally:
        await database.close()

    print(
        f"{len(view.candles):,} 根 K 線："
        f"{view.candles.open_times[0]} → {view.candles.open_times[-1]}"
    )

    renderer = PlotlyActivityHeatmapRenderer()
    multiples = renderer.multiples(view)
    hourly = multiples.mean(axis=0).sort_values()
    print("\n成交筆數的時段節奏（相對於整體平均）")
    print(f"  最冷清：{hourly.index[0]:02d}:00 UTC，{hourly.iloc[0]:.2f} 倍")
    print(f"  最熱鬧：{hourly.index[-1]:02d}:00 UTC，{hourly.iloc[-1]:.2f} 倍")
    print(f"  最熱與最冷相差 {hourly.iloc[-1] / hourly.iloc[0]:.2f} 倍")

    print("\n同一個絕對值在不同基準下的分數（最後一根）")
    for baseline in ActivityBaseline:
        feature = TradingActivity(
            measure=ActivityMeasure.TRADE_COUNT,
            baseline=baseline,
            window=arguments.window if baseline is ActivityBaseline.ROLLING else 20,
        )
        scores = feature.compute(view).dropna()
        if scores.empty:
            print(f"  {baseline}：資料不足")
            continue
        print(
            f"  {baseline}：{scores.iloc[-1]:+.2f}"
            f"（可用 {len(scores):,} 根，超過 +2 的有 {(scores > 2).mean():.2%}）"
        )

    average_true_range = ATR(arguments.atr_period).compute(view)
    latest_close = view.candles.frame["close"].iloc[-1]
    print(
        f"\nATR({arguments.atr_period})：{average_true_range.iloc[-1]:,.2f} USDT"
        f"（收盤價的 {average_true_range.iloc[-1] / latest_close:.2%}）"
    )

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day12-{instrument.storage_key}-activity.html"
    renderer.render(view).write_html(chart_path)
    print(f"圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
