# quantbot/entrypoints/volume_profile_command.py
"""算 Volume Profile，比較逐筆精算與 K 線近似，輸出橫向分布圖。

    uv run python -m quantbot.entrypoints.volume_profile_command \
        --symbol BTC/USDT --market spot --start 2026-07-15 --end 2026-07-16

精算那條路徑需要那段區間的逐筆成交（Day 09 的 backfill_trades_command 補過），
近似那條只要 K 線。兩者都有的時候才印得出差距。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.compare_volume_profiles_application import (
    CompareVolumeProfilesApplication,
)
from quantbot.domain.features.distance_to_point_of_control import (
    DistanceToPointOfControl,
)
from quantbot.domain.services.volume_profile_service import VolumeProfileService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_volume_profile_chart_renderer import (
    PlotlyVolumeProfileChartRenderer,
)
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)
from quantbot.infrastructure.persistence.timescale_trade_repository import (
    TimescaleTradeRepository,
)


def table_for(timeframe: Timeframe) -> str:
    """1m 走原始表，其餘走 Day 07 的 continuous aggregate。"""
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--buckets", type=int, default=100)
    parser.add_argument("--value-area", type=float, default=0.7)
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
    service = VolumeProfileService(
        bucket_count=arguments.buckets, value_area_fraction=arguments.value_area
    )

    database = PostgresDatabase.from_settings()
    candle_repository = TimescaleCandleRepository(
        database, table=table_for(instrument.timeframe)
    )
    application = CompareVolumeProfilesApplication(
        candles=candle_repository,
        trades=TimescaleTradeRepository(database),
        service=service,
    )
    try:
        report = await application.run(instrument, period)
        candles = await candle_repository.read(instrument, period)
    finally:
        await database.close()

    print(
        f"{report.listing.storage_key}：K 線 {report.bar_count:,} 根、"
        f"逐筆成交 {report.trade_row_count:,} 列，{service.bucket_count} 個價格桶"
    )
    for name, profile in (("逐筆精算", report.exact), ("K 線近似", report.approximate)):
        levels = profile.key_levels()
        print(
            f"\n[{name}]"
            f"\n  POC             {levels['point_of_control']:>12,.2f}"
            f"\n  價值區間上緣    {levels['value_area_high']:>12,.2f}"
            f"\n  價值區間下緣    {levels['value_area_low']:>12,.2f}"
            f"\n  總成交量        {profile.total_volume:>12,.3f} BTC"
        )

    print(
        f"\n兩者差距"
        f"\n  POC 相差        {report.point_of_control_difference:>12.4%}"
        f"\n  價值區間重疊    {report.value_area_overlap:>12.2%}"
    )

    view = MarketView(candles=candles)
    distance = DistanceToPointOfControl(window_days=1).compute(view).dropna()
    if not distance.empty:
        print(
            f"\n距離 POC（滾動 1 天，可用 {len(distance):,} 根）"
            f"\n  最後一根        {distance.iloc[-1]:>12.4%}"
            f"\n  絕對值中位數    {distance.abs().median():>12.4%}"
        )

    arguments.out.mkdir(parents=True, exist_ok=True)
    chart_path = arguments.out / f"day14-{instrument.storage_key}-profile.html"
    PlotlyVolumeProfileChartRenderer().render(
        candles, report.exact, report.approximate
    ).write_html(chart_path)
    print(f"\n圖：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
