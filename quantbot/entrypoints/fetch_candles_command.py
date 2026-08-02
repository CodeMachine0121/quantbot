# quantbot/entrypoints/fetch_candles_command.py
"""抓一段月檔 K 線、存成 parquet、畫出 K 線圖。

uv run python -m quantbot.entrypoints.fetch_candles_command
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.binance.binance_candle_csv_parser import (
    BinanceCandleCsvParser,
)
from quantbot.infrastructure.charting.plotly_candle_chart_renderer import (
    PlotlyCandleChartRenderer,
)

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
MONTHS = [f"2026-{month:02d}" for month in range(1, 7)]
DATA_DIRECTORY = Path("data/klines")
CHART_DIRECTORY = Path("notebooks")


def download_monthly_archive(instrument: Instrument, month: str) -> bytes:
    """下載單一月份的 zip。

    今天只抓六個檔、只有一條路徑，所以不需要介面，直接呼叫就好。
    明天要抓幾百個檔、還要在批次與 REST 之間切換，那時候才值得抽一個 CandleSource。
    """
    symbol = instrument.native_symbol
    timeframe = instrument.timeframe
    url = f"{BASE_URL}/{symbol}/{timeframe}/{symbol}-{timeframe}-{month}.zip"
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def main() -> None:
    instrument = Instrument(
        symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1d")
    )
    parser = BinanceCandleCsvParser()

    monthly = [
        CandleSeries(
            instrument, parser.parse(download_monthly_archive(instrument, month))
        )
        for month in MONTHS
    ]
    series = monthly[0]
    for later in monthly[1:]:
        series = series.merge(later)
    series = series.closed_only(pd.Timestamp.now(tz="UTC"))

    # 缺漏偵測今天只是兩行；Day 03 會把它變成 DataIntegrityService
    expected = pd.date_range(
        series.open_times[0],
        series.open_times[-1],
        freq=instrument.timeframe.pandas_frequency,
        tz="UTC",
    )
    missing = expected.difference(series.open_times)

    print(f"{len(series)} 根 K 線：{series.open_times[0]} → {series.open_times[-1]}")
    print(f"缺漏 {len(missing)} 根")
    print(series.frame.dtypes)

    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    CHART_DIRECTORY.mkdir(parents=True, exist_ok=True)
    series.with_identity_columns().to_parquet(
        DATA_DIRECTORY / f"{instrument.storage_key}.parquet"
    )
    PlotlyCandleChartRenderer().render(series).write_html(
        CHART_DIRECTORY / f"day02-{instrument.storage_key}.html"
    )


if __name__ == "__main__":
    main()
