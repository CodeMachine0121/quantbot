# quantbot/domain/values/activity_measure.py
from __future__ import annotations

from enum import StrEnum

import numpy as np
import pandas as pd


class ActivityMeasure(StrEnum):
    """用什麼量「這段時間市場有多熱」。三個角度，答案不一樣。

    - TRADE_COUNT：成交筆數。它衡量**參與者的數量與急迫程度**，跟金額無關；
      一筆 100 BTC 的大單只算一筆。
    - VOLUME：成交量。它衡量**換手的規模**，少數幾張大單就能讓它很高。
    - ABSOLUTE_RETURN：這一根的對數報酬取絕對值。它衡量**價格實際走了多少**，
      跟成交多少無關——大量成交但價格不動（有人在特定價位默默吃貨）與少量成交
      但價格亂跳（沒有流動性）都會發生，前兩個量分不出這兩件事。

    三個一起看才完整。Day 09 那兩根 K 線就是例子：成交量幾乎一樣，成交筆數差 4.2 倍。

    用對數報酬而不是百分比報酬：它可加（連續兩根的對數報酬相加等於兩根合起來的
    對數報酬），所以換粒度時不會累積複利的偏差。
    """

    TRADE_COUNT = "trade_count"
    VOLUME = "volume"
    ABSOLUTE_RETURN = "absolute_return"

    def of(self, candles: pd.DataFrame) -> pd.Series:
        """從 K 線取出（或算出）這個量。轉換只寫在這裡一份。"""
        if self is ActivityMeasure.TRADE_COUNT:
            # trade_count 是可空的 Int64（Day 02 訂的），算 z-score 前要先變 float
            return (candles["trade_count"].astype("Float64").astype("float64")).rename(
                str(self)
            )
        if self is ActivityMeasure.VOLUME:
            return candles["volume"].astype("float64").rename(str(self))
        return self._absolute_log_return(candles["close"]).rename(str(self))

    @staticmethod
    def _absolute_log_return(closes: pd.Series) -> pd.Series:
        """相鄰兩根的對數報酬取絕對值。第 0 筆沒有前一根，所以是 NaN。"""
        values = closes.astype("float64")
        return pd.Series(
            np.abs(np.log(values.to_numpy() / values.shift(1).to_numpy())),
            index=values.index,
        )
