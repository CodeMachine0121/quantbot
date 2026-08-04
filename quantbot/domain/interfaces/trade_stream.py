# quantbot/domain/interfaces/trade_stream.py
from collections.abc import AsyncIterator
from typing import Protocol

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.trade_event import TradeEvent


class TradeStream(Protocol):
    """即時的逐筆成交。

    它回傳 AsyncIterator 而不是「一段資料」：串流沒有結尾，也沒有「這次要抓哪段」
    這個概念。重連、心跳、解析 JSON 全都是實作的內務，domain 只看到一串事件。
    """

    def events(self, listing: Listing) -> AsyncIterator[TradeEvent]: ...
