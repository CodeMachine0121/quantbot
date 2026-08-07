# quantbot/domain/values/order_book_snapshot.py
from dataclasses import dataclass

from quantbot.domain.values.price_level import PriceLevel


@dataclass(frozen=True)
class OrderBookSnapshot:
    """某個瞬間的掛單簿全貌，以及它對應的更新序號。

    last_update_id 是這張快照最重要的欄位，不是附加資訊：接上增量更新流時，
    要靠它判斷哪些更新已經包含在快照裡、該從哪一筆開始套用。
    沒有它，快照就只是一張漂亮但無法延續的圖。
    """

    last_update_id: int
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
