# quantbot/domain/interfaces/trade_source.py
from typing import Protocol

from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange


class TradeSource(Protocol):
    """一條逐筆成交來源：給我一段區間，還我那段成交。

    跟 CandleSource 的差別只有身分——成交沒有 timeframe，所以吃的是 Listing。
    """

    async def load(self, listing: Listing, period: TimeRange) -> TradeSeries: ...
