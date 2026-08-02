# quantbot/domain/services/price_cross_check_service.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.dto.price_cross_check_report import PriceCrossCheckReportDto


class PriceCrossCheckService:
    """跟對照組比日收盤價。

    它驗的是**量級**，不是小數點。跨交易所參考價跟單一交易所的成交價本來就不會
    相等，所以 tolerance 存在的目的是攔「欄位對映錯一格」「時間戳單位搞錯」
    這類差很多的錯誤。

    這個 service 不碰網路：資料誰去拿是 application 的事，比對邏輯留在 domain，
    所以測試只要餵兩張手寫的小 Series。
    """

    def __init__(self, *, tolerance: float = 0.01) -> None:
        self._tolerance = tolerance

    @property
    def tolerance(self) -> float:
        return self._tolerance

    def compare(
        self, ours: pd.Series, theirs: pd.Series, *, reference_name: str
    ) -> PriceCrossCheckReportDto:
        comparison = (
            pd.concat({"ours": ours, "theirs": theirs}, axis=1).dropna().sort_index()
        )
        comparison["relative_difference"] = (
            comparison["ours"] - comparison["theirs"]
        ).abs() / comparison["theirs"]
        comparison["passed"] = comparison["relative_difference"] <= self._tolerance

        return PriceCrossCheckReportDto(
            comparison=comparison,
            tolerance=self._tolerance,
            reference_name=reference_name,
        )
