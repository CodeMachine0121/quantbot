# quantbot/domain/dto/volume_profile_report.py
from __future__ import annotations

from dataclasses import dataclass

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.volume_profile import VolumeProfile


@dataclass(frozen=True)
class VolumeProfileReportDto:
    """同一段行情的兩張 profile，以及它們差多少。

    兩張並排是這份報告的全部意義。單獨看任何一張都看不出近似法放棄了什麼；
    並排之後那個差距是一個可以引用的數字。
    """

    listing: Listing
    trade_row_count: int
    bar_count: int
    exact: VolumeProfile
    approximate: VolumeProfile

    @property
    def point_of_control_difference(self) -> float:
        """兩個 POC 差多少，以精算值的百分比表示。"""
        exact = self.exact.point_of_control
        return (self.approximate.point_of_control - exact) / exact

    @property
    def value_area_overlap(self) -> float:
        """兩個價值區間重疊多少，以精算區間的寬度為分母。

        它比「POC 差多少」更能說明近似法夠不夠用：POC 是一個點，容易因為一兩個桶
        的差異就跳掉；價值區間是一段範圍，重疊率反映的是整體形狀有多接近。
        """
        exact_low, exact_high = self.exact.value_area
        other_low, other_high = self.approximate.value_area
        overlap = min(exact_high, other_high) - max(exact_low, other_low)
        width = exact_high - exact_low
        if width <= 0:
            return float("nan")
        return max(overlap, 0.0) / width
