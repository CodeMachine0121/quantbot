# quantbot/domain/values/time_range.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeRange:
    """半開區間 [start, end)。

    右端開區間是整個專案的慣例：它讓「還沒收完的那一根」自然被排除，
    也讓連續兩段查詢不會在邊界重複拿到同一根 K 線。
    """

    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        for name, moment in (("start", self.start), ("end", self.end)):
            if moment.tz is None:
                raise ValueError(f"{name} 必須是 tz-aware 的 UTC 時間")
        if self.end < self.start:
            raise ValueError(f"end 早於 start：{self.start} → {self.end}")

    @property
    def duration(self) -> pd.Timedelta:
        return self.end - self.start

    def clamp_end(self, latest_end: pd.Timestamp) -> TimeRange:
        """把右端收到 latest_end 以內。用來擋掉還沒收完的那一根。"""
        return TimeRange(self.start, min(self.end, latest_end))

    def is_empty(self) -> bool:
        return self.end <= self.start
