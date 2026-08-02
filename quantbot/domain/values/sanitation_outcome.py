# quantbot/domain/values/sanitation_outcome.py
from dataclasses import dataclass

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries


@dataclass(frozen=True)
class SanitationOutcome:
    """清洗的產出。兩邊都要留：報告要講的是被丟掉的那些列。"""

    accepted: CandleSeries  # 可入庫的
    anomalies: pd.DataFrame  # 所有被標記的列，含仍留在 accepted 裡的那些

    @property
    def rejected_bar_count(self) -> int:
        if self.anomalies.empty:
            return 0
        fatal = self.anomalies[["ohlc_invalid", "negative_value"]].any(axis=1)
        return int(fatal.sum())

    def counts_by_flag(self) -> dict[str, int]:
        flags = ["ohlc_invalid", "negative_value", "zero_volume", "price_jump"]
        if self.anomalies.empty:
            return dict.fromkeys(flags, 0)
        return {flag: int(self.anomalies[flag].sum()) for flag in flags}
