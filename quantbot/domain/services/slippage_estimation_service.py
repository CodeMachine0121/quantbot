# quantbot/domain/services/slippage_estimation_service.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.dto.slippage_estimate_report import SlippageEstimateReportDto
from quantbot.domain.entities.depth_series import DepthSeries


class SlippageEstimationService:
    """從 Day 09 錄下來的掛單簿估一個有根據的滑價，取代拍腦袋給的 0.05%。

    市價單付的滑價由兩部分組成：

    1. **半個價差。** 買要用賣價、賣要用買價，而中間價在兩者正中間，所以一趟就是
       半個價差。這部分算得出來，而且它是下界——不管單多小都要付。
    2. **走簿子的成本。** 單大到吃穿第一檔之後，剩下的量要往更差的價格成交。
       這部分**算不出來**，因為 Day 09 錄下來的是前 5／10／20 檔的加總，
       沒有逐檔價格。所以這裡只能回答「單有沒有小到吃不完前五檔」。

    第二點是 Day 09 那句「先想清楚要算什麼特徵，再決定存什麼」的代價現形。
    要能估價格衝擊就得重新錄一次，而不是重跑一次計算。

    這是 domain service：吃已經在手上的 DepthSeries，回一份報告，沒有任何 I/O。
    """

    def estimate(
        self, depth: DepthSeries, *, order_notional: float
    ) -> SlippageEstimateReportDto:
        if depth.is_empty():
            raise ValueError("沒有掛單簿樣本，估不出滑價")
        if order_notional <= 0.0:
            raise ValueError(f"order_notional 必須 > 0，收到 {order_notional}")

        mid_price = depth.mid_price()
        half_spread_rate = (depth.spread() / 2.0 / mid_price).dropna()
        if half_spread_rate.empty:
            raise ValueError("掛單簿樣本裡沒有有效的價差")

        frame = depth.frame
        top_5_notional = (frame["bid_quantity_5"].clip(lower=0.0) * mid_price).dropna()

        return SlippageEstimateReportDto(
            sample_count=len(half_spread_rate),
            covered_hours=self._covered_hours(depth.captured_times),
            median_half_spread_rate=float(half_spread_rate.median()),
            mean_half_spread_rate=float(half_spread_rate.mean()),
            percentile95_half_spread_rate=float(half_spread_rate.quantile(0.95)),
            median_top_5_notional=float(top_5_notional.median()),
            order_notional=order_notional,
        )

    @staticmethod
    def _covered_hours(moments: pd.DatetimeIndex) -> float:
        """錄製涵蓋了幾個小時。

        用頭尾相減而不是樣本數除以取樣頻率：錄製中斷過的話後者會高估涵蓋範圍，
        而這個數字的用途正是判斷「這份估計有多少代表性」。
        """
        if len(moments) < 2:
            return 0.0
        span = moments.max() - moments.min()
        return float(span / pd.Timedelta(hours=1))
