# quantbot/entrypoints/features_command.py
"""用一份設定檔算出所有特徵，印出一張表的摘要。

    uv run python -m quantbot.entrypoints.features_command \
        --symbol BTC/USDT --market spot --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01

設定檔預設是 quantbot/infrastructure/configuration/features.yaml。
它裡面沒有一行 Python，也不需要 import 任何類別——這是 Day 16 的策略積木庫
能用設定檔表達的前提。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.domain.features.feature_pipeline import FeaturePipeline
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.configuration.yaml_feature_specification_loader import (
    YamlFeatureSpecificationLoader,
)
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

DEFAULT_CONFIGURATION = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "configuration"
    / "features.yaml"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--configuration", type=Path, default=DEFAULT_CONFIGURATION)
    parser.add_argument("--out", type=Path, default=Path("data/features"))
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

    registry = FeatureRegistry()
    specifications = YamlFeatureSpecificationLoader().load(arguments.configuration)
    # 先建管線：設定檔有錯的話在這裡就失敗，不必先花幾秒讀資料
    pipeline = FeaturePipeline(registry.build_all(specifications))

    wanted = ", ".join(sorted(str(item) for item in pipeline.required_inputs))
    print(f"設定檔 {arguments.configuration}")
    print(f"  {len(specifications)} 個特徵，需要原料：{wanted}")
    print(f"  宣告的暖機期 {pipeline.declared_warmup_bar_count} 根")

    database = PostgresDatabase.from_settings()
    application = ComputeFeaturesApplication(
        candles=TimescaleCandleRepository(database, table=table_for(timeframe)),
        trades=TimescaleTradeRepository(database),
        depth=TimescaleDepthRepository(database),
        registry=registry,
    )
    try:
        full = await application.run(
            instrument, period, specifications=specifications, trim_warmup=False
        )
        trimmed = await application.run(
            instrument, period, specifications=specifications
        )
    finally:
        await database.close()

    dropped = len(full) - len(trimmed)
    print(f"\n算完 {full.shape[1]} 欄 × {full.shape[0]:,} 列")
    print(f"切掉暖機期之後剩 {trimmed.shape[0]:,} 列（丟掉 {dropped} 根）")

    print("\n每一欄的可用比例與最後一個值")
    for column in full.columns:
        values = full[column]
        available = f"可用 {values.notna().mean():>7.2%}"
        latest = values.dropna()
        tail = "沒有任何值" if latest.empty else f"最後 {latest.iloc[-1]:>14,.4f}"
        print(f"  {column:<34} {available}  {tail}")

    arguments.out.mkdir(parents=True, exist_ok=True)
    target = arguments.out / f"{instrument.storage_key}_features.parquet"
    trimmed.to_parquet(target)
    print(f"\n落地：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
