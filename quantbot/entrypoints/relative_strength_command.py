# quantbot/entrypoints/relative_strength_command.py
"""讀回補好的 parquet，算 RSI、統計超買超賣的停留長度，輸出雙軸互動圖。

    uv run python -m quantbot.entrypoints.relative_strength_command \
        --symbol BTC/USDT --market spot --timeframe 1h --period 14
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.registry import INDICATORS
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_relative_strength_chart_renderer import (
    PlotlyRelativeStrengthChartRenderer,
)

OVERBOUGHT = 70.0
OVERSOLD = 30.0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--period", type=int, default=14)
    parser.add_argument("--source", type=Path, default=Path("data/klines"))
    parser.add_argument("--out", type=Path, default=Path("notebooks"))
    return parser.parse_args()


def longest_run(flags: pd.Series) -> int:
    """最長一段連續為真有幾根。用來回答「超買狀態能撐多久」。"""
    blocks = (flags != flags.shift()).cumsum()
    lengths = flags.groupby(blocks).sum()
    return int(lengths.max()) if len(lengths) > 0 else 0


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

    # 從註冊表取類別再建實例，走的是 Day 15 特徵管線未來會走的那條路
    line = INDICATORS["rsi"](arguments.period).compute(series)
    valid = line.dropna()
    overbought = valid > OVERBOUGHT
    oversold = valid < OVERSOLD

    print(f"{len(series)} 根 K 線：{series.open_times[0]} → {series.open_times[-1]}")
    print(
        f"RSI > {OVERBOUGHT:.0f}：{int(overbought.sum())} 根"
        f"（{overbought.mean():.2%}），最長連續 {longest_run(overbought)} 根"
    )
    print(
        f"RSI < {OVERSOLD:.0f}：{int(oversold.sum())} 根"
        f"（{oversold.mean():.2%}），最長連續 {longest_run(oversold)} 根"
    )

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day06-{instrument.storage_key}-rsi.html"
    PlotlyRelativeStrengthChartRenderer(period=arguments.period).render(
        series
    ).write_html(chart_path)
    print(f"圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
