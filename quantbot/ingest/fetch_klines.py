"""取得 BTC/USDT 現貨日線 K 線，存成 parquet 並輸出 K 線圖。

用法：
    uv run python -m quantbot.ingest.fetch_klines
"""

from __future__ import annotations

from pathlib import Path

from quantbot.config import settings
from quantbot.ingest.binance_vision import PANDAS_FREQ, find_gaps, load_klines
from quantbot.plotting import plot_ohlcv

# config 裡的 default_symbol 是 ccxt 格式的 "BTC/USDT"，
# 批次檔用的是 "BTCUSDT"。命名怎麼統一是明天 Day 03 的事，今天先手動去掉斜線。
SYMBOL = settings.default_symbol.replace("/", "")
TIMEFRAME = "1d"
MONTHS = [f"2026-{month:02d}" for month in range(1, 7)]

DATA_DIR = Path("data/klines")
CHART_DIR = Path("notebooks")


def main() -> None:
    klines = load_klines(SYMBOL, TIMEFRAME, MONTHS)
    gaps = find_gaps(klines, PANDAS_FREQ[TIMEFRAME])

    print(f"{len(klines)} 根 K 線：{klines.index[0]} → {klines.index[-1]}")
    print(f"缺漏 {len(gaps)} 根")
    print(klines.dtypes)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    klines.to_parquet(DATA_DIR / f"{SYMBOL}-spot-{TIMEFRAME}.parquet")
    chart = plot_ohlcv(klines, f"{SYMBOL} 現貨 {TIMEFRAME}（data.binance.vision）")
    chart.write_html(CHART_DIR / f"day02-{SYMBOL}-{TIMEFRAME}.html")


if __name__ == "__main__":
    main()
