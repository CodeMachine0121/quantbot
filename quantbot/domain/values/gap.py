# quantbot/domain/values/gap.py
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Gap:
    """一段連續缺漏的 K 線。start 與 end 都是開盤時間，兩端皆含。"""

    start: pd.Timestamp
    end: pd.Timestamp
    bar_count: int

    @property
    def duration(self) -> pd.Timedelta:
        return self.end - self.start
