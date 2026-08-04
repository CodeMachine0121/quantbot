# quantbot/domain/values/trade_columns.py
from __future__ import annotations

from typing import ClassVar

import pandas as pd

from quantbot.domain.values.candle_columns import CandleColumns


class TradeColumns:
    """逐筆成交的欄位語彙。CandleColumns 的對應物，只是這裡的一列是一個事件。

    K 線的索引是開盤時間、一根一格；成交的索引是**成交時間**，同一個毫秒裡可以有
    幾十列，所以它 NEVER 是唯一鍵。唯一鍵是 trade_id，去重要看它。

    first_trade_id 與 last_trade_id 不是冗餘欄位。官方的 aggTrades 把「同一張吃單
    在同一個價格上掃到的多筆成交」併成一列，所以一列不等於一筆成交；真正的成交
    筆數是 last - first + 1。少了這兩欄，就沒辦法拿重建出來的 K 線跟官方的
    trade_count 對數字，也偵測不出中間漏了哪幾筆。
    """

    TRANSACT_TIME: ClassVar[str] = "transact_time"
    TRADE_ID: ClassVar[str] = "trade_id"
    FIRST_TRADE_ID: ClassVar[str] = "first_trade_id"
    LAST_TRADE_ID: ClassVar[str] = "last_trade_id"
    INTEGER_COLUMNS: ClassVar[tuple[str, ...]] = (
        TRADE_ID,
        FIRST_TRADE_ID,
        LAST_TRADE_ID,
    )
    PRICE: ClassVar[str] = "price"
    QUANTITY: ClassVar[str] = "quantity"
    BUYER_IS_MAKER: ClassVar[str] = "buyer_is_maker"
    FLOAT_COLUMNS: ClassVar[tuple[str, ...]] = (PRICE, QUANTITY)
    BOOLEAN_COLUMNS: ClassVar[tuple[str, ...]] = (BUYER_IS_MAKER,)

    @classmethod
    def all_columns(cls) -> tuple[str, ...]:
        """落地後的欄位與順序。每條來源都要對齊到這一份。"""
        return cls.INTEGER_COLUMNS + cls.FLOAT_COLUMNS + cls.BOOLEAN_COLUMNS

    @classmethod
    def conform(cls, trades: pd.DataFrame) -> pd.DataFrame:
        """轉型並補齊欄位，讓批次檔與即時串流產出同一種表。

        整數欄用 int64 而不是可空的 Int64：識別碼缺值的成交不存在，允許 NA 只會
        讓「去重」與「找斷號」這兩件事各多一種要考慮的狀態。
        """
        conformed = pd.DataFrame(index=trades.index)
        for column in cls.INTEGER_COLUMNS:
            conformed[column] = trades[column].astype("int64")
        for column in cls.FLOAT_COLUMNS:
            conformed[column] = trades[column].astype("float64")
        for column in cls.BOOLEAN_COLUMNS:
            conformed[column] = trades[column].astype("bool")
        return conformed

    @staticmethod
    def to_utc(epochs: pd.Series) -> pd.Series:
        """epoch 整數轉 UTC 時間。

        這裡直接借 CandleColumns 的單位判斷，因為官方 aggTrades 的時間戳在近年的
        檔案裡是**微秒**，而 K 線一直是毫秒。寫死 unit="ms" 的話時間會落到 1970 年
        附近，而且不會有任何錯誤訊息。用數量級判斷就不必知道哪一年換的。
        """
        return CandleColumns.to_utc(epochs)
