"""把幾個策略並排比較，輸出績效矩陣、相關性，以及 HTML 報告。

    uv run python -m quantbot.entrypoints.compare_strategies_command \
        --timeframe 1h --start 2025-01-01 --end 2026-08-01

預設比較內附的三份設定加上兩個交叉組合。所有策略跑在同一張表、同一組成本假設上，
基準是 BuyAndHold。

跑之前先確認資料是最新的：
    uv run python -m quantbot.entrypoints.ingest_pipeline_command
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.compare_strategies_application import (
    CompareStrategiesApplication,
)
from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.application.generate_signals_application import (
    GenerateSignalsApplication,
)
from quantbot.application.run_backtest_application import RunBacktestApplication
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.services.strategy_correlation_service import (
    StrategyCorrelationService,
)
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_performance_report_renderer import (
    PlotlyPerformanceReportRenderer,
)
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
from quantbot.infrastructure.reporting.text_strategy_comparison_report_renderer import (
    TextStrategyComparisonReportRenderer,
)

STRATEGY_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "configuration"
    / "strategies"
)
SHIPPED = ("trend_ema_rsi", "mean_reversion_vwap", "momentum_breakout")
HOURS_PER_YEAR = 365.0 * 24.0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument(
        "--with-crossed",
        action="store_true",
        default=True,
        help="一併比較兩個交叉組合（Day 18）",
    )
    parser.add_argument("--out", type=Path, default=Path("data/charts"))
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def load_specifications(with_crossed: bool) -> list[StrategySpecification]:
    loader = YamlStrategySpecificationLoader()
    shipped = [loader.load(STRATEGY_DIRECTORY / f"{name}.yaml") for name in SHIPPED]
    if not with_crossed:
        return shipped
    return [
        *shipped,
        shipped[0].with_exit_from(shipped[2]),
        shipped[2].with_exit_from(shipped[0]),
    ]


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
    specifications = load_specifications(arguments.with_crossed)

    database = PostgresDatabase.from_settings()
    assembly = StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )
    metrics = PerformanceMetricsService()
    application = CompareStrategiesApplication(
        backtests=RunBacktestApplication(
            signals=GenerateSignalsApplication(
                features=ComputeFeaturesApplication(
                    candles=TimescaleCandleRepository(
                        database, table=table_for(timeframe)
                    ),
                    trades=TimescaleTradeRepository(database),
                    depth=TimescaleDepthRepository(database),
                    registry=FeatureRegistry(),
                ),
                assembly=assembly,
                engine=StrategyEngine(),
            ),
            backtest=BacktestService(),
        ),
        assembly=assembly,
        metrics=metrics,
        correlation=StrategyCorrelationService(),
    )

    try:
        comparison, reports = await application.run(
            specifications,
            instrument,
            period,
            backtest_specification=BacktestSpecification(
                initial_capital=arguments.capital
            ),
            periods_per_year=HOURS_PER_YEAR,
        )
    finally:
        await database.close()

    renderer = TextStrategyComparisonReportRenderer()
    print(f"{instrument.storage_key}")
    print()
    print(renderer.render(comparison))
    print()
    print(renderer.render_correlation(comparison))

    arguments.out.mkdir(parents=True, exist_ok=True)
    charts = PlotlyPerformanceReportRenderer()
    baseline = reports[-1]
    for report in reports[:-1]:
        target = arguments.out / f"{report.strategy_name}_report.html"
        charts.render(
            report,
            metrics.monthly_returns(report.equity),
            baseline=baseline,
        ).write_html(target)
    overview = arguments.out / "strategy_comparison.html"
    charts.render_comparison(
        comparison, {report.strategy_name: report.equity for report in reports}
    ).write_html(overview)
    print(f"\n圖：{overview} 以及每個策略各一份 *_report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
