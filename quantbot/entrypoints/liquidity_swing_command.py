# quantbot/entrypoints/liquidity_swing_command.py
"""在錄下來的那段資料上，量「被吃掉」與「被撤走」的比例。

    uv run python -m quantbot.entrypoints.liquidity_swing_command \
        --symbol BTC/USDT --market spot --timeframe 1m \
        --start 2026-08-04T17:20 --end 2026-08-04T18:05

這支指令需要三種資料同時存在（K 線、逐筆成交、掛單簿深度），所以它只跑得動
Day 09 錄過的那幾段——現貨的掛單簿歷史在免費資料源裡不存在。
"""

from __future__ import annotations

import argparse
import asyncio

import pandas as pd

from quantbot.domain.features.liquidity_swing import LiquiditySwing
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase
from quantbot.infrastructure.persistence.timescale_candle_repository import (
    TimescaleCandleRepository,
)
from quantbot.infrastructure.persistence.timescale_depth_repository import (
    TimescaleDepthRepository,
)
from quantbot.infrastructure.persistence.timescale_trade_repository import (
    TimescaleTradeRepository,
)

# 完全被成交吃掉的話比例接近 1。低於這個門檻的視為以撤單為主。
CONSUMED_THRESHOLD = 0.5


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--window-seconds", type=float, default=5.0)
    return parser.parse_args()


async def main() -> int:
    arguments = parse_arguments()
    instrument = Instrument(
        symbol=arguments.symbol,
        market=Market(arguments.market),
        timeframe=Timeframe(arguments.timeframe),
    )
    listing = Listing.of(instrument)
    period = TimeRange(
        pd.Timestamp(arguments.start, tz="UTC"), pd.Timestamp(arguments.end, tz="UTC")
    )

    database = PostgresDatabase.from_settings()
    try:
        view = MarketView(
            candles=await TimescaleCandleRepository(database).read(instrument, period),
            trades=await TimescaleTradeRepository(database).read(listing, period),
            depth=await TimescaleDepthRepository(database).read(listing, period),
        )
    finally:
        await database.close()

    print(
        f"{listing.storage_key}：K 線 {len(view.candles):,} 根、"
        f"成交 {len(view.require_trades()):,} 筆、"
        f"深度取樣 {len(view.require_depth()):,} 筆"
    )

    for side in ExtremeSide:
        feature = LiquiditySwing(side=side, window_seconds=arguments.window_seconds)
        ratio = feature.consumed_ratio(view).dropna()
        if ratio.empty:
            print(f"\n[{side}] 沒有可用的樣本")
            continue
        consumed = ratio > CONSUMED_THRESHOLD
        print(f"\n[{side}] {feature.name}")
        print(f"  可用樣本 {len(ratio):,} 筆")
        print(
            f"  中位數 {ratio.median():.3f}、"
            f"四分位 {ratio.quantile(0.25):.3f} / {ratio.quantile(0.75):.3f}"
        )
        print(
            f"  以成交吃掉為主（> {CONSUMED_THRESHOLD}）："
            f"{int(consumed.sum()):,} 筆（{consumed.mean():.2%}）"
        )
        print(
            f"  以撤單為主：{int((~consumed).sum()):,} 筆（{(~consumed).mean():.2%}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
