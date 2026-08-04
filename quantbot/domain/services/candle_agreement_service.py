# quantbot/domain/services/candle_agreement_service.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.dto.candle_agreement_report import CandleAgreementReportDto
from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.candle_columns import CandleColumns


class CandleAgreementService:
    """比對兩份 K 線是否逐欄一致。

    Day 03 的 PriceCrossCheckService 比的是「我們跟外部參考價的量級對不對」，
    容忍度是 1%，因為那是兩個不同市場的價格。這裡不一樣：兩邊都是同一個交易所的
    同一段成交，只是一邊是官方聚合好的、一邊是我們自己從逐筆成交重建的。它們應該
    **幾乎完全相等**，所以容忍度是浮點誤差的量級。

    這是逐筆成交這層資料唯一拿得到的對照組——外面沒有免費的第二個 tick 來源。
    它一次擔保五件事：欄位對映、時間戳單位、時區、聚合邊界、taker 方向。
    """

    def __init__(self, *, tolerance: float = 1e-6) -> None:
        self._tolerance = tolerance

    @property
    def tolerance(self) -> float:
        return self._tolerance

    def compare(
        self, rebuilt: CandleSeries, official: CandleSeries
    ) -> CandleAgreementReportDto:
        shared = rebuilt.open_times.intersection(official.open_times)
        ours = rebuilt.frame.loc[shared]
        theirs = official.frame.loc[shared]

        return CandleAgreementReportDto(
            compared_bar_count=len(shared),
            missing_in_rebuilt=len(official.open_times.difference(rebuilt.open_times)),
            missing_in_official=len(rebuilt.open_times.difference(official.open_times)),
            maximum_relative_difference={
                column: self._maximum_relative_difference(ours[column], theirs[column])
                for column in CandleColumns.all_columns()
                if column in ours and column in theirs
            },
            tolerance=self._tolerance,
        )

    @staticmethod
    def _maximum_relative_difference(ours: pd.Series, theirs: pd.Series) -> float:
        """相對誤差的最大值。分母為 0 的那幾格改看絕對差。

        成交量那幾欄在冷清的一分鐘裡真的會是 0，用相對誤差會變成 0/0；
        把那幾格換成絕對差，才不會讓一個合法的 0 產生 NaN 或 inf。
        """
        difference = (ours.astype("float64") - theirs.astype("float64")).abs()
        scale = theirs.astype("float64").abs()
        relative = difference.where(scale == 0.0, difference / scale)
        return 0.0 if relative.empty else float(relative.max())
