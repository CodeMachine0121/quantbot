# quantbot/application/evaluate_imbalance_power_application.py
from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

import pandas as pd

from quantbot.domain.dto.imbalance_power_report import ImbalancePowerReportDto
from quantbot.domain.dto.predictive_power_report import PredictivePowerReportDto
from quantbot.domain.features.order_book_imbalance import OrderBookImbalance
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.interfaces.depth_repository import DepthRepository
from quantbot.domain.services.predictive_power_service import PredictivePowerService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange


class EvaluateImbalancePowerApplication:
    """讀出掛單簿與 K 線，算 OBI，量它對未來報酬有沒有資訊。

    它跑兩種粒度：

    - **原始取樣**：每秒一筆的 OBI 對未來 N 秒的中間價報酬。這是這個特徵的
      主場——它衰減得快，秒級才是它該被檢驗的尺度。
    - **聚合到 K 線**：每根 K 線一個 OBI 對未來 N 根的收盤價報酬。這是它進策略
      引擎之後實際會被用到的形狀。

    未來報酬那一側用中間價而不是最後成交價：掛單簿的兩側報價本來就在手上，
    而中間價不會被「最後一筆恰好是主動賣」這種單筆事件帶偏。
    """

    # 每筆取樣之間允許的最大時間差。取樣間隔設 1 秒，給 5 倍的餘裕吸收
    # 事件迴圈的抖動；再大就代表中間真的斷過，那種配對不該進統計。
    DEFAULT_MAXIMUM_NATIVE_STEP: ClassVar[pd.Timedelta] = pd.Timedelta(seconds=5)

    def __init__(
        self,
        *,
        candles: CandleRepository,
        depth: DepthRepository,
        power: PredictivePowerService,
        native_horizons: Sequence[int] = (1, 5, 30),
        bar_horizons: Sequence[int] = (1, 3),
        maximum_native_step: pd.Timedelta | None = None,
    ) -> None:
        self._candles = candles
        self._depth = depth
        self._power = power
        self._native_horizons = tuple(native_horizons)
        self._bar_horizons = tuple(bar_horizons)
        self._maximum_native_step = (
            maximum_native_step or self.DEFAULT_MAXIMUM_NATIVE_STEP
        )

    async def run(
        self,
        instrument: Instrument,
        period: TimeRange,
        *,
        features: Sequence[OrderBookImbalance],
    ) -> ImbalancePowerReportDto:
        listing = Listing.of(instrument)
        view = MarketView(
            candles=await self._candles.read(instrument, period),
            depth=await self._depth.read(listing, period),
        )
        depth = view.require_depth()

        return ImbalancePowerReportDto(
            listing=listing,
            depth_sample_count=len(depth),
            bar_count=len(view.candles),
            native_reports=self._evaluate(
                view, features=features, horizons=self._native_horizons, native=True
            ),
            bar_reports=self._evaluate(
                view, features=features, horizons=self._bar_horizons, native=False
            ),
        )

    def _evaluate(
        self,
        view: MarketView,
        *,
        features: Sequence[OrderBookImbalance],
        horizons: tuple[int, ...],
        native: bool,
    ) -> tuple[PredictivePowerReportDto, ...]:
        depth = view.require_depth()
        prices = depth.mid_price() if native else view.candles.frame["close"]
        # 原始取樣是不規則的，而且錄製中斷過的話中間有空白：一段跨越空白的
        # 「往後一筆」實際上跨了幾十分鐘。上限跟著 horizon 放大，因為往後 30 筆
        # 本來就該花 30 倍的時間。K 線那一側每根等距，不需要這個上限。
        return tuple(
            self._power.evaluate(
                feature.ratio(depth.frame) if native else feature.compute(view),
                self._power.forward_returns(
                    prices,
                    horizon=horizon,
                    maximum_step=(
                        self._maximum_native_step * horizon if native else None
                    ),
                ),
            )
            for feature in features
            for horizon in horizons
        )
