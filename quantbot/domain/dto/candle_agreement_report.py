# quantbot/domain/dto/candle_agreement_report.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CandleAgreementReportDto:
    """重建出來的 K 線跟官方 K 線差多少，逐欄一個數字。

    只留最大相對誤差而不是整張比對表：這份報告要能印在終端機上被看完。
    真的要逐根追的話，重跑一次比對就有了，報告不是資料的家。
    """

    compared_bar_count: int
    missing_in_rebuilt: int
    missing_in_official: int
    maximum_relative_difference: Mapping[str, float]
    tolerance: float

    @property
    def worst_column(self) -> str:
        """誤差最大的那一欄。欄位對映錯一格的話，錯的那一欄會遠遠突出。"""
        if not self.maximum_relative_difference:
            return ""
        return max(
            self.maximum_relative_difference,
            key=lambda column: self.maximum_relative_difference[column],
        )

    @property
    def passed(self) -> bool:
        return (
            self.compared_bar_count > 0
            and self.missing_in_rebuilt == 0
            and self.missing_in_official == 0
            and all(
                difference <= self.tolerance
                for difference in self.maximum_relative_difference.values()
            )
        )
