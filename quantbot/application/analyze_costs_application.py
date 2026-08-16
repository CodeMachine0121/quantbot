# quantbot/application/analyze_costs_application.py
from __future__ import annotations

from collections.abc import Sequence

from quantbot.application.generate_signals_application import (
    GenerateSignalsApplication,
)
from quantbot.domain.dto.cost_sensitivity_report import CostSensitivityReportDto
from quantbot.domain.dto.slippage_estimate_report import SlippageEstimateReportDto
from quantbot.domain.interfaces.depth_repository import DepthRepository
from quantbot.domain.services.cost_sensitivity_service import CostSensitivityService
from quantbot.domain.services.slippage_estimation_service import (
    SlippageEstimationService,
)
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange


class AnalyzeCostsApplication:
    """兩件事：從掛單簿估滑價，以及掃一遍費率看策略在哪裡由賺轉賠。

    兩者刻意是兩個方法而不是一個。滑價的估計只需要掛單簿，費率掃描只需要訊號，
    而它們的資料來源與可用範圍完全不同——掛單簿只有錄製的那幾段，K 線有整段歷史。
    綁成一個方法的話，一個沒有掛單簿的期間就連費率掃描都跑不了。
    """

    def __init__(
        self,
        *,
        signals: GenerateSignalsApplication,
        depth: DepthRepository,
        slippage: SlippageEstimationService,
        sensitivity: CostSensitivityService,
    ) -> None:
        self._signals = signals
        self._depth = depth
        self._slippage = slippage
        self._sensitivity = sensitivity

    async def estimate_slippage(
        self,
        instrument: Instrument,
        period: TimeRange,
        *,
        order_notional: float,
    ) -> SlippageEstimateReportDto | None:
        """回 None 代表這段期間沒有錄到掛單簿，而不是滑價為零。

        兩者要分得開：沒有資料的時候該做的事是「沿用一個保守的假設並標注它是假設」，
        NEVER 是「當成沒有滑價」。
        """
        depth = await self._depth.read(Listing.of(instrument), period)
        if depth.is_empty():
            return None
        return self._slippage.estimate(depth, order_notional=order_notional)

    async def scan_fee_rates(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
        *,
        initial_capital: float,
        taker_fee_rates: Sequence[float],
        slippage_rate: float,
    ) -> CostSensitivityReportDto:
        signals = await self._signals.run(specification, instrument, period)
        return self._sensitivity.scan(
            signals,
            initial_capital=initial_capital,
            taker_fee_rates=taker_fee_rates,
            slippage_rate=slippage_rate,
        )
