# quantbot/domain/values/trade_event.py
from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.taker_side import TakerSide


@dataclass(frozen=True)
class TradeEvent:
    """即時串流推來的一筆成交。

    它跟 TradeSeries 裡的一列是同一件事的兩種形狀：串流一次來一筆，所以是物件；
    落地與計算一次處理幾十萬筆，所以是 DataFrame。轉換發生在 application 把
    緩衝區倒出來的那一刻，NEVER 一筆一筆寫進資料庫。
    """

    transact_time: pd.Timestamp
    trade_id: int
    first_trade_id: int
    last_trade_id: int
    price: float
    quantity: float
    buyer_is_maker: bool

    @property
    def taker_side(self) -> TakerSide:
        return TakerSide.from_buyer_is_maker(self.buyer_is_maker)
