# quantbot/domain/dto/data_integrity_report.py
from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.gap import Gap


@dataclass(frozen=True)
class DataIntegrityReportDto:
    """一段期間的資料完整性。算一次、傳下去，NEVER 在報告階段重算。"""

    expected_bar_count: int
    actual_bar_count: int
    gaps: tuple[Gap, ...]

    @property
    def missing_bar_count(self) -> int:
        return sum(gap.bar_count for gap in self.gaps)

    @property
    def coverage_ratio(self) -> float:
        if self.expected_bar_count == 0:
            return 1.0
        return self.actual_bar_count / self.expected_bar_count

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    def to_frame(self) -> pd.DataFrame:
        """給報告與 CSV 用的表。"""
        return pd.DataFrame(
            [
                {
                    "gap_start": gap.start,
                    "gap_end": gap.end,
                    "missing_bar_count": gap.bar_count,
                }
                for gap in self.gaps
            ],
            columns=["gap_start", "gap_end", "missing_bar_count"],
        )
