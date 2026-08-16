# quantbot/domain/services/cost_sensitivity_service.py
from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from quantbot.domain.dto.cost_sensitivity_report import (
    CostSensitivityReportDto,
    CostSensitivityRowDto,
)
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.cost_model import CostModel
from quantbot.domain.values.strategy_signals import StrategySignals


class CostSensitivityService:
    """同一組訊號，換幾種成本假設各跑一次，找出它在哪一點由賺轉賠。

    它不用重算訊號——部位序列跟成本無關，只有權益曲線有關。所以整個掃描的成本
    是「幾次向量化乘法」，跟訊號那一段比可以忽略。

    它注入 BacktestService 而不是自己算：回測的算式只該有一份，而多一份的下場是
    敏感度分析與主線回測用不同的成本模型，於是兩邊的數字對不起來卻沒人發現。
    Domain service 注入 domain service 沒有問題，兩者都是純計算、都不吃 Protocol。
    """

    def __init__(self, *, backtest: BacktestService) -> None:
        self._backtest = backtest

    def scan(
        self,
        signals: StrategySignals,
        *,
        initial_capital: float,
        taker_fee_rates: Sequence[float],
        slippage_rate: float,
    ) -> CostSensitivityReportDto:
        if not taker_fee_rates:
            raise ValueError("至少要有一個費率")

        ordered = sorted(taker_fee_rates)
        rows = tuple(
            self._row(
                signals,
                initial_capital=initial_capital,
                taker_fee_rate=rate,
                slippage_rate=slippage_rate,
            )
            for rate in ordered
        )
        reference = self._backtest.run(
            signals,
            BacktestSpecification(
                initial_capital=initial_capital, costs=CostModel.frictionless()
            ),
        )

        return CostSensitivityReportDto(
            strategy_name=signals.strategy.name,
            trade_count=reference.trade_count,
            turnover=reference.turnover,
            gross_total_return=reference.gross_total_return,
            rows=rows,
            break_even_round_trip_rate=self._break_even(rows),
        )

    def _row(
        self,
        signals: StrategySignals,
        *,
        initial_capital: float,
        taker_fee_rate: float,
        slippage_rate: float,
    ) -> CostSensitivityRowDto:
        report = self._backtest.run(
            signals,
            BacktestSpecification(
                initial_capital=initial_capital,
                costs=CostModel(
                    taker_fee_rate=taker_fee_rate, slippage_rate=slippage_rate
                ),
            ),
        )
        return CostSensitivityRowDto(
            taker_fee_rate=taker_fee_rate,
            slippage_rate=slippage_rate,
            total_return=report.total_return,
            cost_paid=report.cost_paid,
            cost_share_of_gross_profit=report.cost_share_of_gross_profit,
        )

    @staticmethod
    def _break_even(rows: tuple[CostSensitivityRowDto, ...]) -> float | None:
        """由賺轉賠發生在哪個來回成本率，用線性內插。

        兩種情況回 None：最低的成本假設下就已經賠錢（那個點不存在），
        或者最高的成本假設下還在賺（只知道它在網格之外，而回一個網格端點會被
        誤讀成「剛好在這裡由賺轉賠」）。
        """
        if rows[0].total_return <= 0.0:
            return None
        if rows[-1].total_return > 0.0:
            return None

        for earlier, later in pairwise(rows):
            if earlier.total_return > 0.0 >= later.total_return:
                span = earlier.total_return - later.total_return
                if span == 0.0:
                    return earlier.round_trip_rate
                weight = earlier.total_return / span
                return earlier.round_trip_rate + weight * (
                    later.round_trip_rate - earlier.round_trip_rate
                )
        return None
