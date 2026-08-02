# quantbot/domain/values/pipeline_configuration.py
from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.instrument import Instrument


@dataclass(frozen=True)
class PipelineConfiguration:
    """管線要顧哪些東西。純資料，由 infrastructure 的 YAML loader 建出來。"""

    instruments: tuple[Instrument, ...]
    history_start: pd.Timestamp
    maximum_concurrency: int = 4
    cross_check_tolerance: float = 0.01
    cross_check_sample_days: int = 5

    def __post_init__(self) -> None:
        if not self.instruments:
            raise ValueError("設定檔裡沒有任何 instrument")
        if self.history_start.tz is None:
            raise ValueError("history_start 必須是 tz-aware 的 UTC 時間")
