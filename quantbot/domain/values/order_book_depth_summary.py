# quantbot/domain/values/order_book_depth_summary.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.depth_columns import DepthColumns


@dataclass(frozen=True)
class DepthQuantity:
    """在前 level 檔以內，兩側各掛了多少量。

    它只為 OrderBookDepthSummary 存在，所以住在同一個檔案；
    哪天有第二個對象用到它，再搬出去。
    """

    level: int
    bid_quantity: float
    ask_quantity: float


@dataclass(frozen=True)
class OrderBookDepthSummary:
    """某個瞬間的掛單簿，壓縮成落地得起的幾個數字。

    完整的掛單簿一秒可以變動幾百次，全部留下來一天就是幾十 GB。這個值是刻意的
    有損壓縮：留下最好的買賣價（價差算得出來）與幾個深度的加總（掛單不對稱算得
    出來），其餘丟掉。丟掉的東西包含「單一大額掛單」與「掛單的分布形狀」——
    要那些的話得另外設計落地格式，不是改一個參數。
    """

    captured_at: pd.Timestamp
    best_bid_price: float
    best_ask_price: float
    depth_quantities: tuple[DepthQuantity, ...]

    @property
    def spread(self) -> float:
        """買賣價差，以報價幣計。"""
        return self.best_ask_price - self.best_bid_price

    @property
    def mid_price(self) -> float:
        """中間價。價差窄的時候它比最後成交價更接近「現在的價格」。"""
        return (self.best_bid_price + self.best_ask_price) / 2.0

    def as_row(self) -> dict[str, float]:
        """攤成一列，欄名由 DepthColumns 決定。"""
        row = {
            "best_bid_price": self.best_bid_price,
            "best_ask_price": self.best_ask_price,
        }
        for quantity in self.depth_quantities:
            row[DepthColumns.bid_quantity(quantity.level)] = quantity.bid_quantity
            row[DepthColumns.ask_quantity(quantity.level)] = quantity.ask_quantity
        return row
