# quantbot/application/run_backtest_application.py
from __future__ import annotations

import pandas as pd

from quantbot.application.generate_signals_application import (
    GenerateSignalsApplication,
)
from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange


class RunBacktestApplication:
    """一份策略設定 ＋ 一段時間 → 一份回測結果。

    它把讀資料與算訊號都交給 GenerateSignalsApplication，自己只多做一步：把部位
    序列與收盤價交給 BacktestService。這樣的分工讓 Day 21 的組合搜尋可以只讀一次
    資料就跑幾百個策略——那條路徑用的是 evaluate()，不是 run()。
    """

    def __init__(
        self,
        *,
        signals: GenerateSignalsApplication,
        backtest: BacktestService,
    ) -> None:
        self._signals = signals
        self._backtest = backtest

    async def run(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
        *,
        backtest_specification: BacktestSpecification,
        trial_count: int = 1,
    ) -> BacktestReportDto:
        signals = await self._signals.run(specification, instrument, period)
        return self._backtest.run(
            signals, backtest_specification, trial_count=trial_count
        )

    async def load_table(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
    ) -> pd.DataFrame:
        return await self._signals.load_table(specification, instrument, period)

    def evaluate(
        self,
        strategy: Strategy,
        table: pd.DataFrame,
        *,
        backtest_specification: BacktestSpecification,
        trial_count: int = 1,
    ) -> BacktestReportDto:
        """資料已經在手上時的入口。同一張表可以跑任意多個策略。"""
        signals = self._signals.engine.signals(strategy, table)
        return self._backtest.run(
            signals, backtest_specification, trial_count=trial_count
        )
