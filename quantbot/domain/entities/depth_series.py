# quantbot/domain/entities/depth_series.py
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.order_book_depth_summary import OrderBookDepthSummary
from quantbot.domain.values.time_range import TimeRange


class DepthSeries:
    """一連串掛單簿深度摘要，排成時間序列。

    它跟 CandleSeries 有一個關鍵差別：**索引是不規則的**。K 線每根都存在、間隔固定；
    深度摘要只在錄製程式活著的時候有，而且錄製頻率跟 K 線的粒度沒有關係。所以任何
    要把它跟 K 線放在一起用的地方，都得先過 aligned_to()——直接 concat 兩張索引不同
    的表，pandas 會安靜地產出一張全是 NaN 的結果。
    """

    def __init__(self, listing: Listing, depth: pd.DataFrame) -> None:
        self.listing = listing
        self._depth = DepthColumns.conform(depth)

    @classmethod
    def empty(cls, listing: Listing) -> DepthSeries:
        index = pd.DatetimeIndex([], tz="UTC", name=DepthColumns.CAPTURED_AT)
        return cls(listing, pd.DataFrame(index=index))

    @classmethod
    def of_summaries(
        cls, listing: Listing, summaries: Iterable[OrderBookDepthSummary]
    ) -> DepthSeries:
        rows = list(summaries)
        if not rows:
            return cls.empty(listing)
        index = pd.DatetimeIndex(
            [summary.captured_at for summary in rows], name=DepthColumns.CAPTURED_AT
        )
        return cls(listing, pd.DataFrame([row.as_row() for row in rows], index=index))

    @property
    def frame(self) -> pd.DataFrame:
        return self._depth

    @property
    def captured_times(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self._depth.index)

    def __len__(self) -> int:
        return len(self._depth)

    def is_empty(self) -> bool:
        return self._depth.empty

    def restricted_to(self, period: TimeRange) -> DepthSeries:
        times = self.captured_times
        selected = (times >= period.start) & (times < period.end)
        return DepthSeries(self.listing, self._depth.loc[selected])

    def spread(self) -> pd.Series:
        """買賣價差。取名 spread 而不是 bid_ask_spread：這是業界的正式說法。"""
        return (self._depth["best_ask_price"] - self._depth["best_bid_price"]).rename(
            "spread"
        )

    def mid_price(self) -> pd.Series:
        return (
            (self._depth["best_ask_price"] + self._depth["best_bid_price"]) / 2.0
        ).rename("mid_price")
