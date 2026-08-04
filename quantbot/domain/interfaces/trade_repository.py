# quantbot/domain/interfaces/trade_repository.py
from typing import Protocol

from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange


class TradeRepository(Protocol):
    """逐筆成交的持久化。一個 entity 一個 repository。"""

    async def save(self, series: TradeSeries, *, source: str) -> int:
        """寫入並回傳實際新增的列數。重複的列由主鍵擋掉，所以重跑是安全的。"""
        ...

    async def read(self, listing: Listing, period: TimeRange) -> TradeSeries: ...

    async def latest_trade_id(self, listing: Listing) -> int | None:
        """已經存到哪一筆。即時串流接續歷史批次時要靠它決定從哪裡開始信任資料。"""
        ...
