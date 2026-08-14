"""用一份策略設定檔算出訊號與部位，印出一份摘要。

    uv run python -m quantbot.entrypoints.signals_command \
        --strategy trend_ema_rsi --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01

設定檔在 quantbot/infrastructure/configuration/strategies/ 底下，
裡面沒有一行 Python。要試另一組參數就複製一份 YAML 改幾個數字。

跑之前先確認資料是最新的：
    uv run python -m quantbot.entrypoints.ingest_pipeline_command
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.application.generate_signals_application import (
    GenerateSignalsApplication,
)
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.strategy_signals import StrategySignals
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.configuration.yaml_strategy_specification_loader import (
    YamlStrategySpecificationLoader,
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

STRATEGY_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "configuration"
    / "strategies"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="trend_ema_rsi")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def report(signals: StrategySignals) -> None:
    strategy = signals.strategy
    print(f"\n{strategy.describe()}")
    print(f"\n  K 線 {signals.bar_count:,} 根")
    print(f"  進場訊號 {signals.entry_signal_count:>6} 根")
    print(f"  出場訊號 {int(signals.exit_signals.sum()):>6} 根")
    print(f"  被過濾否決 {signals.vetoed_entry_count:>4} 根")
    print(f"  實際交易 {signals.trade_count:>6} 筆")
    print(f"  持有 {signals.held_bar_count:,} 根（曝險 {signals.exposure:.2%}）")


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
    path = STRATEGY_DIRECTORY / f"{arguments.strategy}.yaml"

    # 載入與組裝都在讀資料之前：設定檔有錯就在這裡失敗
    specification = YamlStrategySpecificationLoader().load(path)
    assembly = StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )
    assembly.assemble(specification)
    print(f"設定檔 {path.name} 載入成功")

    database = PostgresDatabase.from_settings()
    application = GenerateSignalsApplication(
        features=ComputeFeaturesApplication(
            candles=TimescaleCandleRepository(database, table=table_for(timeframe)),
            trades=TimescaleTradeRepository(database),
            depth=TimescaleDepthRepository(database),
            registry=FeatureRegistry(),
        ),
        assembly=assembly,
        engine=StrategyEngine(),
    )
    try:
        signals = await application.run(specification, instrument, period)
        table = signals.table
        baseline = await application.run_assembled(Strategy.buy_and_hold(), table)
    finally:
        await database.close()

    report(signals)
    report(baseline)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
