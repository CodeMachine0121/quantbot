# quantbot/domain/dto/slippage_estimate_report.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlippageEstimateReportDto:
    """從錄下來的掛單簿估出來的滑價，以及那個估計的適用範圍。

    它刻意把「估出來的數字」與「這個數字憑什麼」放在同一份報告裡。半個價差是市價單
    一定要付的部分，而它只是滑價的下界——上界要看下的單有多大，那就是 top_5_notional
    那幾個欄位在回答的事。

    sample_count 與 covered_hours 一定要印出來。這份估計來自錄製程式活著的那幾段，
    而那幾段是不是有代表性（是不是剛好都在冷清時段）沒有辦法從數字本身看出來。
    """

    sample_count: int
    covered_hours: float
    median_half_spread_rate: float
    mean_half_spread_rate: float
    percentile95_half_spread_rate: float
    median_top_5_notional: float
    order_notional: float

    @property
    def order_fits_in_top_5(self) -> bool:
        """要下的單吃不吃得完前五檔。

        吃不完的話，半個價差就是滑價的合理估計；吃得完的話還要加上走簿子的成本，
        而那個成本算不出來——錄下來的是前 5／10／20 檔的**加總**，沒有逐檔價格。
        """
        return self.order_notional <= self.median_top_5_notional

    @property
    def suggested_slippage_rate(self) -> float:
        """建議用哪個數字當回測的滑價。

        取 95 百分位而不是中位數，因為訊號常常出現在波動放大的時候，而價差跟波動
        是同向的——用中位數估會系統性地低估策略實際付出的滑價。
        """
        return self.percentile95_half_spread_rate
