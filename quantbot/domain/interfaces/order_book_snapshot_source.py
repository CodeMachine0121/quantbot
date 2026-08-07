# quantbot/domain/interfaces/order_book_snapshot_source.py
from typing import Protocol

from quantbot.domain.values.listing import Listing
from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot


class OrderBookSnapshotSource(Protocol):
    """掛單簿的全貌快照。

    它跟 OrderBookStream 是兩條路徑、兩個介面：快照走 REST 一次取回全貌，
    增量走 WebSocket 持續推送。序號斷裂之後要重來的是**快照**，所以這條路徑
    在跑的過程中會被反覆呼叫，不是只在啟動時用一次。
    """

    async def snapshot(self, listing: Listing, *, depth: int) -> OrderBookSnapshot: ...
