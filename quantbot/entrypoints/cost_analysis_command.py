"""把成本加回去：從掛單簿估滑價、掃一遍費率、畫加成本前後的權益曲線。

    uv run python -m quantbot.entrypoints.cost_analysis_command \
        --strategy trend_ema_rsi --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01

掛單簿只有 Day 09 錄下來的那幾段，所以滑價估計可能回「沒有資料」。那時候該做的事
是沿用一個保守的假設並標注它是假設，NEVER 當成沒有滑價。

跑之前先確認資料是最新的：
    uv run python -m quantbot.entrypoints.ingest_pipeline_command
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.analyze_costs_application import AnalyzeCostsApplication
from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.application.generate_signals_application import (
    GenerateSignalsApplication,
)
from quantbot.application.run_backtest_application import RunBacktestApplication
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.cost_sensitivity_service import CostSensitivityService
from quantbot.domain.services.slippage_estimation_service import (
    SlippageEstimationService,
)
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.cost_model import CostModel
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_cost_comparison_renderer import (
    PlotlyCostComparisonRenderer,
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
from quantbot.infrastructure.reporting.text_cost_sensitivity_report_renderer import (
    TextCostSensitivityReportRenderer,
)

STRATEGY_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "configuration"
    / "strategies"
)
# Binance 現貨的 taker 費率階梯：0.1% 是一般用戶，0.02% 大約是 VIP 高階 ＋ BNB 折抵。
# 網格兩端刻意超出真實範圍：0 是理想回測（等於毛報酬），0.2% 是「如果交易所漲價」，
# 而兩端都在網格內，由賺轉賠的位置才內插得出來。
FEE_RATES = (0.0, 0.0002, 0.0004, 0.0006, 0.0008, 0.001, 0.0015, 0.002)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="trend_ema_rsi")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument(
        "--depth-start",
        default=None,
        help="估滑價要用哪一段掛單簿。預設跟回測期間相同，但掛單簿只有 Day 09"
        " 錄下來的那幾段，所以多數情況要另外指定",
    )
    parser.add_argument("--depth-end", default=None)
    parser.add_argument("--out", type=Path, default=Path("data/charts"))
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def depth_period(arguments: argparse.Namespace, fallback: TimeRange) -> TimeRange:
    """估滑價用哪一段掛單簿。

    預設跟回測期間相同，但那個預設多半會回「沒有資料」——掛單簿只有自己錄的
    那幾段（Day 09），而回測期間是整段歷史。分開指定比偷偷把範圍放大好：
    「這個滑價是用另一段時間的掛單簿估的」是一個必須被看見的假設。
    """
    if arguments.depth_start is None or arguments.depth_end is None:
        return fallback
    return TimeRange(
        pd.Timestamp(arguments.depth_start, tz="UTC"),
        pd.Timestamp(arguments.depth_end, tz="UTC"),
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

    specification = YamlStrategySpecificationLoader().load(
        STRATEGY_DIRECTORY / f"{arguments.strategy}.yaml"
    )
    assembly = StrategyAssemblyService(
        features=FeatureRegistry(), conditions=ConditionRegistry()
    )
    strategy = assembly.assemble(specification)

    database = PostgresDatabase.from_settings()
    signals = GenerateSignalsApplication(
        features=ComputeFeaturesApplication(
            candles=TimescaleCandleRepository(database, table=table_for(timeframe)),
            trades=TimescaleTradeRepository(database),
            depth=TimescaleDepthRepository(database),
            registry=FeatureRegistry(),
        ),
        assembly=assembly,
        engine=StrategyEngine(),
    )
    backtest = BacktestService()
    costs = AnalyzeCostsApplication(
        signals=signals,
        depth=TimescaleDepthRepository(database),
        slippage=SlippageEstimationService(),
        sensitivity=CostSensitivityService(backtest=backtest),
    )
    backtests = RunBacktestApplication(signals=signals, backtest=backtest)

    try:
        estimate = await costs.estimate_slippage(
            instrument,
            depth_period(arguments, period),
            order_notional=arguments.capital,
        )
        slippage_rate = (
            estimate.suggested_slippage_rate if estimate is not None else 0.0005
        )
        sensitivity = await costs.scan_fee_rates(
            specification,
            instrument,
            period,
            initial_capital=arguments.capital,
            taker_fee_rates=FEE_RATES,
            slippage_rate=slippage_rate,
        )
        table = await backtests.load_table(specification, instrument, period)
        charged = BacktestSpecification(
            initial_capital=arguments.capital,
            costs=CostModel(taker_fee_rate=0.001, slippage_rate=slippage_rate),
        )
        report = backtests.evaluate(strategy, table, backtest_specification=charged)
        baseline = backtests.evaluate(
            Strategy.buy_and_hold(), table, backtest_specification=charged
        )
    finally:
        await database.close()

    renderer = TextCostSensitivityReportRenderer()
    print(f"{instrument.storage_key}  {period.start.date()} → {period.end.date()}")
    print()
    print(renderer.render_slippage(estimate))
    print()
    print(renderer.render(sensitivity))

    arguments.out.mkdir(parents=True, exist_ok=True)
    charts = PlotlyCostComparisonRenderer()
    equity_path = arguments.out / f"{arguments.strategy}_cost_comparison.html"
    charts.render(report, baseline=baseline).write_html(equity_path)
    sensitivity_path = arguments.out / f"{arguments.strategy}_cost_sensitivity.html"
    charts.render_sensitivity(
        [row.round_trip_rate for row in sensitivity.rows],
        [row.total_return for row in sensitivity.rows],
    ).write_html(sensitivity_path)
    print(f"\n圖：{equity_path}\n   {sensitivity_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
