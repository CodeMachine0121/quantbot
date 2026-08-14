"""跑一份策略設定的回測，並跟 BuyAndHold 基準並排。

    uv run python -m quantbot.entrypoints.backtest_command \
        --strategy trend_ema_rsi --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01

--ideal 跑理想回測（無手續費、無滑價）；--show-look-ahead 額外跑一次把訊號位移
關掉的版本，用來看未來函數會讓報酬離譜到什麼程度。後者的數字 NEVER 當結論。

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
from quantbot.application.run_backtest_application import RunBacktestApplication
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
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
from quantbot.infrastructure.reporting.text_backtest_report_renderer import (
    TextBacktestReportRenderer,
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
    parser.add_argument("--exit-from", default=None)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--ideal", action="store_true", help="不計手續費與滑價")
    parser.add_argument(
        "--show-look-ahead",
        action="store_true",
        help="額外跑一次關掉訊號位移的版本（示範未來函數，不是結論）",
    )
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def build_application(
    database: PostgresDatabase,
    timeframe: Timeframe,
    assembly: StrategyAssemblyService,
    *,
    signal_delay_bars: int = 1,
) -> RunBacktestApplication:
    return RunBacktestApplication(
        signals=GenerateSignalsApplication(
            features=ComputeFeaturesApplication(
                candles=TimescaleCandleRepository(database, table=table_for(timeframe)),
                trades=TimescaleTradeRepository(database),
                depth=TimescaleDepthRepository(database),
                registry=FeatureRegistry(),
            ),
            assembly=assembly,
            engine=StrategyEngine(signal_delay_bars=signal_delay_bars),
        ),
        backtest=BacktestService(),
    )


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

    loader = YamlStrategySpecificationLoader()
    specification = loader.load(STRATEGY_DIRECTORY / f"{arguments.strategy}.yaml")
    if arguments.exit_from is not None:
        specification = specification.with_exit_from(
            loader.load(STRATEGY_DIRECTORY / f"{arguments.exit_from}.yaml")
        )
    assembly = StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )
    strategy = assembly.assemble(specification)

    backtest_specification = (
        BacktestSpecification.ideal(arguments.capital)
        if arguments.ideal
        else BacktestSpecification(initial_capital=arguments.capital)
    )

    database = PostgresDatabase.from_settings()
    application = build_application(database, timeframe, assembly)
    try:
        table = await application.load_table(specification, instrument, period)
        reports = [
            application.evaluate(
                strategy, table, backtest_specification=backtest_specification
            ),
            application.evaluate(
                Strategy.buy_and_hold(),
                table,
                backtest_specification=backtest_specification,
            ),
        ]
        if arguments.show_look_ahead:
            cheating = build_application(
                database, timeframe, assembly, signal_delay_bars=0
            )
            reports.append(
                cheating.evaluate(
                    Strategy(
                        name=f"{strategy.name}_look_ahead",
                        entry=strategy.entry,
                        exit=strategy.exit,
                        filters=strategy.filters,
                        holding=strategy.holding,
                        direction=strategy.direction,
                    ),
                    table,
                    backtest_specification=backtest_specification,
                )
            )
    finally:
        await database.close()

    print(f"{instrument.storage_key}  {period.start.date()} → {period.end.date()}")
    renderer = TextBacktestReportRenderer()
    for report in reports:
        print()
        print(renderer.render(report))

    if arguments.show_look_ahead:
        honest, _, cheat = reports
        print(
            f"\n關掉訊號位移的差別："
            f"{honest.total_return:+.2%} → {cheat.total_return:+.2%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
