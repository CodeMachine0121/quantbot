# quantbot/entrypoints/crossover_chart_command.py
"""讀回補好的 parquet，算兩條 SMA、找出交叉，印出訊號並輸出互動圖。

    uv run python -m quantbot.entrypoints.crossover_chart_command \
        --symbol BTC/USDT --market spot --timeframe 1h --fast 20 --slow 60
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.crossover_signals import CrossoverSignals
from quantbot.domain.indicators.sma import SMA
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_crossover_chart_renderer import (
    PlotlyCrossoverChartRenderer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=60)
    parser.add_argument("--source", type=Path, default=Path("data/klines"))
    parser.add_argument("--out", type=Path, default=Path("notebooks"))
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    instrument = Instrument(
        symbol=arguments.symbol,
        market=Market(arguments.market),
        timeframe=Timeframe(arguments.timeframe),
    )
    series = CandleSeries(
        instrument,
        pd.read_parquet(arguments.source / f"{instrument.storage_key}.parquet"),
    )

    # 這裡是組裝根：指標、訊號、圖表三個具體型別只在這一支檔案裡碰面
    fast = SMA(arguments.fast, expected_timeframe=instrument.timeframe)
    slow = SMA(arguments.slow, expected_timeframe=instrument.timeframe)
    crosses = CrossoverSignals(fast.compute(series), slow.compute(series))

    # 事件那一根與最快能成交的那一根並排，差的那一根就是位移
    events = pd.DataFrame(
        {
            "golden": crosses.golden,
            "entry": crosses.entry,
            "death": crosses.death,
            "exit": crosses.exit,
        }
    )
    fired = events.loc[events.any(axis=1)]

    print(f"{len(series)} 根 K 線：{series.open_times[0]} → {series.open_times[-1]}")
    print(
        f"黃金交叉 {int(crosses.golden.sum())} 次，"
        f"死亡交叉 {int(crosses.death.sum())} 次"
    )
    print(fired.head(10))

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day04-{instrument.storage_key}-crossover.html"
    PlotlyCrossoverChartRenderer(
        fast_period=arguments.fast, slow_period=arguments.slow
    ).render(series).write_html(chart_path)
    print(f"圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
