# quantbot/application/analyze_breakouts_application.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.dto.breakout_statistics_report import BreakoutStatisticsReportDto
from quantbot.domain.features.average_true_range import ATR
from quantbot.domain.features.breakout import Breakout
from quantbot.domain.features.trading_activity import TradingActivity
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.services.breakout_labelling_service import (
    BreakoutLabellingService,
)
from quantbot.domain.services.breakout_statistics_service import (
    BreakoutStatisticsService,
)
from quantbot.domain.values.activity_measure import ActivityMeasure
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange


class AnalyzeBreakoutsApplication:
    """統計真假突破，以及兩組在突破當下有什麼可觀察的差異。

    它組出來的三個對照量全部是**突破當下就在手上**的：

    - 突破幅度除以 ATR：勉強擦過去的突破，是不是比較容易失敗。
    - 成交筆數的 z-score：沒人跟進的突破，是不是比較容易失敗。
    - 這一根的絕對報酬 z-score：突破那一根本身有多猛。

    標籤來自未來（那是 labelling service 的事），對照量一律來自當下。
    這條界線是這個用例唯一真正重要的設計，混掉就變成用未來解釋未來。
    """

    def __init__(
        self,
        *,
        candles: CandleRepository,
        labelling: BreakoutLabellingService,
        statistics: BreakoutStatisticsService,
        activity_window: int = 168,
        atr_period: int = 14,
    ) -> None:
        self._candles = candles
        self._labelling = labelling
        self._statistics = statistics
        self._activity_window = activity_window
        self._atr_period = atr_period

    async def run(
        self, instrument: Instrument, period: TimeRange, *, breakout: Breakout
    ) -> BreakoutStatisticsReportDto:
        view = MarketView(candles=await self._candles.read(instrument, period))
        labels = self._labelling.label(view, breakout)

        return self._statistics.summarize(
            labels,
            self._observations(view, breakout),
            horizon=self._labelling.horizon,
        )

    def _observations(
        self, view: MarketView, breakout: Breakout
    ) -> dict[str, pd.Series]:
        average_true_range = ATR(self._atr_period).compute(view)
        return {
            "excess_over_atr": breakout.excess(view) / average_true_range,
            "trade_count_z": TradingActivity(
                measure=ActivityMeasure.TRADE_COUNT, window=self._activity_window
            ).compute(view),
            "absolute_return_z": TradingActivity(
                measure=ActivityMeasure.ABSOLUTE_RETURN, window=self._activity_window
            ).compute(view),
        }
