# quantbot/domain/dto/price_cross_check_report.py
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PriceCrossCheckReportDto:
    """跟對照組比對的結果。"""

    comparison: pd.DataFrame  # 逐日的兩邊收盤價、相對差、是否通過
    tolerance: float
    reference_name: str

    @property
    def maximum_relative_difference(self) -> float:
        if self.comparison.empty:
            return 0.0
        return float(self.comparison["relative_difference"].max())

    @property
    def passed(self) -> bool:
        return bool(self.comparison["passed"].all())

    @property
    def flagged_days(self) -> pd.DataFrame:
        return self.comparison.loc[~self.comparison["passed"]]
