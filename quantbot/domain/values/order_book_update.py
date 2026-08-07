# quantbot/domain/values/order_book_update.py
from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.price_level import PriceLevel


@dataclass(frozen=True)
class OrderBookUpdate:
    """一筆增量更新：這段序號區間內，哪幾檔的掛量變成了多少。

    它帶的是**區間**而不是單一序號（first_update_id 到 final_update_id），
    因為交易所會把同一個時間窗內的多次變動打包成一筆推送。
    序號連不連續要拿區間的兩端去比，只看一端會漏掉整包。

    這裡只描述「發生了什麼變動」，不判斷「這筆該不該套用」——後者是
    OrderBookSequenceService 的工作。
    """

    event_time: pd.Timestamp
    first_update_id: int
    final_update_id: int
    bid_changes: tuple[PriceLevel, ...]
    ask_changes: tuple[PriceLevel, ...]
