# quantbot/domain/values/depth_columns.py
from __future__ import annotations

from typing import ClassVar

import pandas as pd


class DepthColumns:
    """掛單簿深度摘要的欄位語彙。

    這裡的 LEVELS 不是一個「參數」，是 schema 的一部分：一旦錄下來的是前 5／10／20
    檔的加總，事後就再也算不出前 7 檔——原始的逐檔資料沒有被留下來。所以深度清單
    只寫在這一個地方，錄製端與資料表都從它產生，NEVER 讓兩邊各寫一份。

    要改這個清單的代價是重新錄一次，不是重跑一次計算。這個代價要在文章裡講清楚，
    也是「先想清楚要算什麼特徵，再決定存什麼」這句話的具體樣子。
    """

    CAPTURED_AT: ClassVar[str] = "captured_at"
    LEVELS: ClassVar[tuple[int, ...]] = (5, 10, 20)
    BEST_COLUMNS: ClassVar[tuple[str, ...]] = ("best_bid_price", "best_ask_price")

    @classmethod
    def bid_quantity(cls, level: int) -> str:
        return f"bid_quantity_{level}"

    @classmethod
    def ask_quantity(cls, level: int) -> str:
        return f"ask_quantity_{level}"

    @classmethod
    def quantity_columns(cls) -> tuple[str, ...]:
        return tuple(
            column
            for level in cls.LEVELS
            for column in (cls.bid_quantity(level), cls.ask_quantity(level))
        )

    @classmethod
    def all_columns(cls) -> tuple[str, ...]:
        return cls.BEST_COLUMNS + cls.quantity_columns()

    @classmethod
    def conform(cls, depth: pd.DataFrame) -> pd.DataFrame:
        """轉型並補齊欄位。缺的欄位補 NaN 而不是 0——0 是「掛量真的是零」，
        跟「這個深度沒有錄」是完全不同的意思。"""
        conformed = pd.DataFrame(index=depth.index)
        for column in cls.all_columns():
            conformed[column] = (
                depth[column].astype("float64")
                if column in depth
                else pd.Series(float("nan"), index=depth.index, dtype="float64")
            )
        return conformed.sort_index()
