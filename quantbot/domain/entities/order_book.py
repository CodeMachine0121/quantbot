# quantbot/domain/entities/order_book.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.order_book_depth_summary import (
    DepthQuantity,
    OrderBookDepthSummary,
)
from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.price_level import PriceLevel


class OrderBook:
    """本地維護的一份掛單簿。全系列唯一一個**有狀態**的 entity。

    前面所有東西都是「一段資料進來、一個結果出去」。掛單簿不是：它是一個狀態機，
    現在的樣子取決於初始快照與之後每一筆增量更新是否都正確套用過。這個差別決定了
    它的測試方式——要驗的不是某次計算的輸出，而是**一連串操作之後的狀態**。

    兩側各用一個 dict（價格 → 掛量）。這裡刻意不是 DataFrame：增量更新一次只動
    十幾檔，每一筆都重建一張表的話，一分鐘幾千筆更新會直接跟不上。全系列「NEVER
    用 for loop」針對的是遍歷幾十萬根 K 線，不是遍歷一筆更新裡的十幾檔掛單。
    """

    def __init__(self, snapshot: OrderBookSnapshot) -> None:
        self._bids: dict[float, float] = {
            level.price: level.quantity for level in snapshot.bids
        }
        self._asks: dict[float, float] = {
            level.price: level.quantity for level in snapshot.asks
        }
        self._last_update_id = snapshot.last_update_id

    @property
    def last_update_id(self) -> int:
        """本地簿子目前反映到哪一筆更新。序號校驗要拿它去比。"""
        return self._last_update_id

    @property
    def best_bid_price(self) -> float:
        return max(self._bids) if self._bids else float("nan")

    @property
    def best_ask_price(self) -> float:
        return min(self._asks) if self._asks else float("nan")

    def __len__(self) -> int:
        """兩側的總檔數。快照抓 100 檔，跑一陣子之後通常會比這個多。"""
        return len(self._bids) + len(self._asks)

    def apply(self, update: OrderBookUpdate) -> None:
        """套用一筆增量更新。

        呼叫端 MUST 先問過 OrderBookSequenceService 這筆該不該套——這個方法
        NEVER 自己檢查序號。理由是「該不該套」是規則、屬於 domain service，
        「怎麼套」是狀態轉移、屬於這個 entity；混在一起的話，兩者都測不乾淨。
        """
        self._apply_side(self._bids, update.bid_changes)
        self._apply_side(self._asks, update.ask_changes)
        self._last_update_id = update.final_update_id

    def summarize(self, captured_at: pd.Timestamp) -> OrderBookDepthSummary:
        """壓成落地得起的幾個數字。深度清單由 DepthColumns 決定，不是參數。

        買方要價格最高的前 N 檔，賣方要價格最低的前 N 檔——兩邊的「前面」
        是反方向的。這個反向排序寫錯的症狀是掛單不對稱的正負號整批顛倒，
        而數值範圍看起來完全正常。
        """
        descending_bids = sorted(self._bids.items(), reverse=True)
        ascending_asks = sorted(self._asks.items())

        return OrderBookDepthSummary(
            captured_at=captured_at,
            best_bid_price=self.best_bid_price,
            best_ask_price=self.best_ask_price,
            depth_quantities=tuple(
                DepthQuantity(
                    level=level,
                    bid_quantity=sum(
                        quantity for _, quantity in descending_bids[:level]
                    ),
                    ask_quantity=sum(
                        quantity for _, quantity in ascending_asks[:level]
                    ),
                )
                for level in DepthColumns.LEVELS
            ),
        )

    @staticmethod
    def _apply_side(side: dict[float, float], changes: tuple[PriceLevel, ...]) -> None:
        """掛量 0 是「這一檔清空了」，要移除而不是留一個掛 0 的價位。

        留著的話它會被算進深度加總的分母（值是 0，不影響加總），但會佔掉一個
        「前 N 檔」的位置，讓 N 檔實際上只涵蓋 N-1 檔真實掛單。
        """
        for level in changes:
            if level.is_removal:
                side.pop(level.price, None)
            else:
                side[level.price] = level.quantity
