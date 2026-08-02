# quantbot/entrypoints/smoothing_comparison_command.py
"""讀回補好的 parquet，在跌得最急的一段上對照 SMA 與 EMA，輸出互動圖。

    uv run python -m quantbot.entrypoints.smoothing_comparison_command \
        --symbol BTC/USDT --market spot --timeframe 1h --period 20
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.ema import EMA
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_smoothing_comparison_renderer import (
    PlotlySmoothingComparisonRenderer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--period", type=int, default=20)
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

    renderer = PlotlySmoothingComparisonRenderer(period=arguments.period)
    # 切片在 renderer 裡是最後一步：兩條線先在完整資料上算完，段落才切得出正確的暖機
    segment = renderer.steepest_drop(series)
    flips = renderer.direction_flips(series)

    print(f"{len(series)} 根 K 線：{series.open_times[0]} → {series.open_times[-1]}")
    print(
        f"跌最急的一段：{segment.open_times[0]} → {segment.open_times[-1]}"
        f"（{len(segment)} 根）"
    )
    print(f"換方向次數：SMA {flips['sma']} 次，EMA {flips['ema']} 次")
    warmup = EMA(arguments.period).required_warmup_bar_count()
    print(f"EMA({arguments.period}) 建議預留的暖機根數：{warmup}")

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day05-{instrument.storage_key}-smoothing.html"
    renderer.render(series, segment).write_html(chart_path)
    print(f"圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
