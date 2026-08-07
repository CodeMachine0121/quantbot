# quantbot/domain/dto/breakout_statistics_report.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationContrastDto:
    """一個「突破當下就觀察得到」的量，在守住與被打回來兩組之間差多少。

    用中位數而不是平均：突破當下的成交量分布右尾很長（少數幾次暴量可以是平常的
    幾十倍），平均會被那幾次主導，而我們要問的是「一般情況下有沒有差」。
    """

    name: str
    held_median: float
    failed_median: float

    @property
    def difference(self) -> float:
        return self.held_median - self.failed_median

    @property
    def ratio(self) -> float:
        """守住組是被打回來組的幾倍。分母為 0 時回 NaN，NEVER 回 inf。"""
        if self.failed_median == 0.0:
            return float("nan")
        return self.held_median / self.failed_median


@dataclass(frozen=True)
class BreakoutStatisticsReportDto:
    """真假突破的統計。

    held_ratio 是這份報告最容易被誤讀的數字。它**不是勝率**——它只說「突破之後
    N 根之內沒有跌回突破價位」的比例，跟進場價、出場規則、手續費都沒有關係。
    一個 62% 的 held_ratio 完全可以對應到一個賠錢的策略，因為守住時賺 1 塊、
    被打回來時賠 3 塊也是 62%。
    """

    event_count: int
    held_count: int
    horizon: int
    favourable_median: Mapping[str, float]
    adverse_median: Mapping[str, float]
    contrasts: tuple[ObservationContrastDto, ...]

    @property
    def failed_count(self) -> int:
        return self.event_count - self.held_count

    @property
    def held_ratio(self) -> float:
        return self.held_count / self.event_count if self.event_count else float("nan")
