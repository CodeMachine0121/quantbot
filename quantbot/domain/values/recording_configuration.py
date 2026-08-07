# quantbot/domain/values/recording_configuration.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.listing import Listing


@dataclass(frozen=True)
class RecordingConfiguration:
    """錄一段即時資料要決定的事。

    capture_interval_seconds 是這幾個參數裡最貴的一個：掛單簿一秒可以變動幾百次，
    每次變動都存一列的話，一天就是幾十 GB，而且大部分相鄰的兩列幾乎一樣。
    每秒摘要一次是刻意的取捨——夠細到看得出短線壓力，又小到存得起。

    倒緩衝有兩個觸發條件，兩個都要有：

    - flush_row_count：攢夠一批再寫，讓寫入不變成瓶頸。
    - flush_interval_seconds：**上限**。只看列數的話，冷清時段可能幾十分鐘都湊不滿
      一批，而那段時間裡程式一旦掛掉，緩衝裡的東西就沒了。深度摘要每秒一列，
      湊滿 5,000 列要 83 分鐘——沒有時間上限的話，那 83 分鐘的資料一直只存在記憶體裡。
    """

    listing: Listing
    snapshot_depth: int = 100
    capture_interval_seconds: float = 1.0
    flush_row_count: int = 5_000
    flush_interval_seconds: float = 30.0
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.capture_interval_seconds <= 0:
            raise ValueError("capture_interval_seconds 必須大於 0")
        if self.flush_row_count < 1:
            raise ValueError("flush_row_count 必須 >= 1")
        if self.flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds 必須大於 0")

    @property
    def capture_interval(self) -> pd.Timedelta:
        return pd.Timedelta(seconds=self.capture_interval_seconds)
