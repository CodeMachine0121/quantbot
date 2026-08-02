# quantbot/domain/interfaces/candle_repository.py
from typing import Protocol

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.time_range import TimeRange


class CandleRepository(Protocol):
    """K 線的持久化。一個 entity 一個 repository，讀與寫都在這裡。"""

    async def save(self, series: CandleSeries, *, source: str) -> int:
        """寫入並回傳實際新增的列數。重複的列由主鍵擋掉，所以重跑是安全的。"""
        ...

    async def read(self, instrument: Instrument, period: TimeRange) -> CandleSeries: ...

    async def existing_open_times(
        self, instrument: Instrument, period: TimeRange
    ) -> pd.DatetimeIndex:
        """已經有哪些開盤時間。缺漏偵測只需要索引，不需要把整段資料撈出來。"""
        ...
