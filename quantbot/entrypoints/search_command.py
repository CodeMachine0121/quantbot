"""跑一整個組合搜尋，並在打亂順序的假資料上跑同一套當對照。

    uv run python -m quantbot.entrypoints.search_command \
        --strategy trend_ema_rsi --timeframe 1h \
        --start 2025-01-01 --end 2026-08-01

兩份報告並排：真實資料一份、把報酬順序打亂的假資料一份。假資料裡完全沒有任何
依賴順序的訊號，所以在它上面「找到」的漂亮結果全部來自搜尋本身。

跑之前先確認資料是最新的：
    uv run python -m quantbot.entrypoints.ingest_pipeline_command
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.application.search_combinations_application import (
    SearchCombinationsApplication,
)
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)
from quantbot.domain.services.return_shuffle_service import ReturnShuffleService
from quantbot.domain.services.search_space_service import SearchSpaceService
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.services.trial_deflation_service import TrialDeflationService
from quantbot.domain.services.walk_forward_service import WalkForwardService
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.search_space import (
    ConditionParameterAxis,
    ConditionTree,
    FeatureParameterAxis,
    IncreasingPeriodConstraint,
    SearchSpace,
)
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.infrastructure.charting.plotly_search_distribution_renderer import (
    PlotlySearchDistributionRenderer,
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
from quantbot.infrastructure.reporting.text_search_report_renderer import (
    TextSearchReportRenderer,
)

STRATEGY_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "configuration"
    / "strategies"
)
HOURS_PER_YEAR = 365.0 * 24.0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="trend_ema_rsi")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--market", default="spot", choices=[m.value for m in Market])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--shuffle-seed", type=int, default=20261005)
    parser.add_argument("--out", type=Path, default=Path("data/charts"))
    return parser.parse_args()


def table_for(timeframe: Timeframe) -> str:
    return "candles" if timeframe.value == "1m" else f"candles_{timeframe}"


def trend_search_space(base: StrategySpecification) -> SearchSpace:
    """趨勢策略的搜尋空間：兩條 EMA 的週期加上 RSI 的閾值。

    3 × 4 × 4 = 48 種，剪枝之後剩下講得通的那些（快線週期必須小於慢線）。
    這個數字刻意不大——48 種已經足以讓「挑最漂亮的那一個」失去意義，而那正是
    今天要示範的事。
    """
    return SearchSpace(
        base=base,
        axes=(
            FeatureParameterAxis(feature_index=0, key="period", values=(8, 12, 21)),
            FeatureParameterAxis(
                feature_index=1, key="period", values=(21, 26, 34, 55)
            ),
            ConditionParameterAxis(
                tree=ConditionTree.FILTERS, key="value", values=(60, 65, 70, 75)
            ),
        ),
        constraints=(
            IncreasingPeriodConstraint(faster_feature_index=0, slower_feature_index=1),
        ),
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
    space = trend_search_space(specification)

    database = PostgresDatabase.from_settings()
    application = SearchCombinationsApplication(
        features=ComputeFeaturesApplication(
            candles=TimescaleCandleRepository(database, table=table_for(timeframe)),
            trades=TimescaleTradeRepository(database),
            depth=TimescaleDepthRepository(database),
            registry=FeatureRegistry(),
        ),
        assembly=StrategyAssemblyService(
            features=FeatureRegistry(), conditions=ConditionRegistry()
        ),
        engine=StrategyEngine(),
        backtest=BacktestService(),
        space=SearchSpaceService(features=FeatureRegistry()),
        walk_forward=WalkForwardService(),
        metrics=PerformanceMetricsService(),
        deflation=TrialDeflationService(),
        shuffle=ReturnShuffleService(),
    )
    backtest_specification = BacktestSpecification(initial_capital=arguments.capital)

    try:
        view = await application.load_view(specification, instrument, period)
    finally:
        await database.close()

    actual = application.search(
        space,
        view,
        label="真實資料",
        backtest_specification=backtest_specification,
        periods_per_year=HOURS_PER_YEAR,
    )
    shuffled = application.search(
        space,
        application.shuffled_view(view, seed=arguments.shuffle_seed),
        label=f"打亂順序（seed {arguments.shuffle_seed}）",
        backtest_specification=backtest_specification,
        periods_per_year=HOURS_PER_YEAR,
    )

    renderer = TextSearchReportRenderer()
    print(f"{instrument.storage_key}  {period.start.date()} → {period.end.date()}")
    for report in (actual, shuffled):
        print()
        print(renderer.render(report))

    print(
        f"\n兩邊的最佳樣本內夏普：真實 {actual.best_in_sample_sharpe:+.3f}"
        f" vs 打亂 {shuffled.best_in_sample_sharpe:+.3f}"
    )

    arguments.out.mkdir(parents=True, exist_ok=True)
    charts = PlotlySearchDistributionRenderer()
    distribution = arguments.out / f"{arguments.strategy}_search_distribution.html"
    charts.render(actual, shuffled).write_html(distribution)
    scatter = arguments.out / f"{arguments.strategy}_search_in_versus_out.html"
    charts.render_in_versus_out(actual).write_html(scatter)
    print(f"\n圖：{distribution}\n   {scatter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
