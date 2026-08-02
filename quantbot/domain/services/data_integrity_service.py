# quantbot/domain/services/data_integrity_service.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.dto.data_integrity_report import DataIntegrityReportDto
from quantbot.domain.values.gap import Gap
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe


class DataIntegrityService:
    """實際資料相對於完整時間軸缺了哪幾段。

    這是全專案唯一的缺漏偵測。Day 03 拿它產回補報告、Day 08 拿它盤點資料庫，
    兩邊問的是同一個問題，所以 NEVER 各寫一份。
    """

    def inspect(
        self,
        open_times: pd.DatetimeIndex,
        *,
        period: TimeRange,
        timeframe: Timeframe,
    ) -> DataIntegrityReportDto:
        if len(open_times) and open_times.tz is None:
            raise ValueError("open_times 必須是 tz-aware，時區在入庫前就要統一")

        expected = timeframe.expected_open_times(period)
        actual = open_times.tz_convert("UTC") if len(open_times) else open_times
        missing = expected.difference(actual)

        return DataIntegrityReportDto(
            expected_bar_count=len(expected),
            actual_bar_count=len(expected.intersection(actual)),
            gaps=self._group_into_gaps(missing, timeframe.step),
        )

    @staticmethod
    def _group_into_gaps(
        missing: pd.DatetimeIndex, step: pd.Timedelta
    ) -> tuple[Gap, ...]:
        """把連續的缺漏點合併成區間。沒有迴圈遍歷時間軸。"""
        if missing.empty:
            return ()

        moments = missing.to_series()
        # 與前一筆的距離不等於一個 step，就是新的一段。
        # 第一筆的 diff 是 NaT，比較結果為 True，剛好當成第一段的開頭。
        block_identifiers = (moments.diff() != step).cumsum()
        return tuple(
            Gap(start=block.iloc[0], end=block.iloc[-1], bar_count=len(block))
            for _, block in moments.groupby(block_identifiers)
        )
