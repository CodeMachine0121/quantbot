# quantbot/application/compare_strategies_application.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from quantbot.application.run_backtest_application import RunBacktestApplication
from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.dto.strategy_comparison_report import StrategyComparisonReportDto
from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.services.strategy_correlation_service import (
    StrategyCorrelationService,
)
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange


class CompareStrategiesApplication:
    """幾份策略設定 → 一份並排比較的報告。

    **一張表跑完所有策略**，這是公平比較的第一個條件，而它也是唯一一個容易做錯的：
    每個策略各自呼叫一次 run() 會各自讀一次資料，而不同的設定宣告不同的特徵，
    於是暖機期不同、資料長度不同、報酬率不可比。所以這裡先把所有設定的特徵取聯集
    算成一張表，再讓每個策略在同一張表上跑。

    基準策略也在同一張表上跑，所以「贏過基準幾個百分點」是同一段時間的比較。
    """

    def __init__(
        self,
        *,
        backtests: RunBacktestApplication,
        assembly: StrategyAssemblyService,
        metrics: PerformanceMetricsService,
        correlation: StrategyCorrelationService,
    ) -> None:
        self._backtests = backtests
        self._assembly = assembly
        self._metrics = metrics
        self._correlation = correlation

    async def run(
        self,
        specifications: Sequence[StrategySpecification],
        instrument: Instrument,
        period: TimeRange,
        *,
        backtest_specification: BacktestSpecification,
        periods_per_year: float,
    ) -> tuple[StrategyComparisonReportDto, tuple[BacktestReportDto, ...]]:
        """回報告與原始回測結果，後者給圖表用。

        兩個一起回而不是讓呼叫端再跑一次：重跑會多讀一次資料，而更糟的是
        圖上的數字有機會跟表上的不一樣。
        """
        if not specifications:
            raise ValueError("至少要有一份策略設定")

        merged = self._merged_specification(specifications)
        table = await self._backtests.load_table(merged, instrument, period)

        reports = tuple(
            self._backtests.evaluate(
                self._assembly.assemble(specification),
                table,
                backtest_specification=backtest_specification,
            )
            for specification in specifications
        )
        baseline = self._backtests.evaluate(
            Strategy.buy_and_hold(),
            table,
            backtest_specification=backtest_specification,
        )

        summaries = tuple(
            self._metrics.summarize(report, periods_per_year=periods_per_year)
            for report in reports
        )
        correlation = self._correlation.matrix(
            {report.strategy_name: report.returns for report in reports}
        )
        comparison = StrategyComparisonReportDto(
            period_label=f"{period.start.date()} → {period.end.date()}",
            baseline=self._metrics.summarize(
                baseline, periods_per_year=periods_per_year
            ),
            summaries=summaries,
            correlation=correlation,
        )
        return comparison, (*reports, baseline)

    @staticmethod
    def _merged_specification(
        specifications: Sequence[StrategySpecification],
    ) -> StrategySpecification:
        """把所有設定的特徵併成一份，只為了算出那張共用的表。

        它回傳的設定不會被組裝成策略——它的條件樹只是第一份設定的，沒有意義。
        它存在的唯一目的是帶著完整的特徵清單去算表。
        """
        merged = specifications[0]
        seen = {feature.describe(): feature for feature in merged.features}
        for specification in specifications[1:]:
            for feature in specification.features:
                seen.setdefault(feature.describe(), feature)
        return replace(merged, features=tuple(seen.values()))
