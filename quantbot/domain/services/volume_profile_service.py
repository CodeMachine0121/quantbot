# quantbot/domain/services/volume_profile_service.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.trade_columns import TradeColumns
from quantbot.domain.values.volume_profile import VolumeProfile


class VolumeProfileService:
    """把成交量按價格分桶，做出價格軸上的分布。

    兩條路徑，因為兩種資料都拿得到，而它們的差別是這一天的重點：

    - from_trades：**精算**。每一筆成交都知道自己的價格，直接丟進對應的價格桶。
    - from_candles：**近似**。一根 K 線只有四個價格與一個總量，所以必須假設那個量
      在某個價格上（或某個範圍內）。假設不同，畫出來的分布就不同。

    近似的誤差不是小數點後幾位的問題。一根 1 分鐘 K 線的成交散落在整個高低範圍裡，
    而近似法把它全部塞在一個點上，於是分布會出現實際上不存在的尖峰。這一天要做的
    就是把那個差距量出來。
    """

    def __init__(
        self, *, bucket_count: int = 100, value_area_fraction: float = 0.7
    ) -> None:
        if bucket_count < 2:
            raise ValueError(f"bucket_count 必須 >= 2，收到 {bucket_count}")
        self._bucket_count = bucket_count
        self._value_area_fraction = value_area_fraction

    @property
    def bucket_count(self) -> int:
        return self._bucket_count

    def from_trades(self, trades: TradeSeries) -> VolumeProfile:
        """用逐筆成交精算。每一筆都知道自己的成交價，不需要任何假設。"""
        frame = trades.frame
        return self._profile(
            frame[TradeColumns.PRICE].to_numpy(dtype="float64"),
            frame[TradeColumns.QUANTITY].to_numpy(dtype="float64"),
        )

    def from_candles(self, candles: CandleSeries) -> VolumeProfile:
        """用 K 線近似。把每一根的成交量整份放在它的典型價上。

        典型價 (高 + 低 + 收) / 3 是慣例，但**放在哪裡都是猜的**。其他常見的選擇
        是收盤價、或是把量平均攤在高低之間。三種都會產生不同的分布，而沒有哪一種
        能還原真相——真相在逐筆成交裡。

        這個方法存在的理由是實務的：逐筆成交一天七十幾萬列，要算一年的 profile
        得處理兩億多列；K 線一年五十幾萬根。所以近似法會被用，而用它的人應該知道
        自己放棄了什麼。
        """
        frame = candles.frame
        typical = (
            frame[["high", "low", "close"]].astype("float64").sum(axis=1) / 3.0
        ).to_numpy()
        return self._profile(typical, frame["volume"].to_numpy(dtype="float64"))

    def _profile(self, prices: np.ndarray, volumes: np.ndarray) -> VolumeProfile:
        """分桶。用 np.histogram 的 weights 參數一次完成，沒有一行在遍歷資料。

        桶的邊界由資料的最高最低價決定，所以兩條路徑算出來的桶**不一定一樣**——
        逐筆成交的極值會比 K 線的高低價更極端嗎？不會，K 線的高低價就是那段時間
        的成交極值。所以邊界會一致，兩張分布才比較得起來。
        """
        if len(prices) == 0:
            raise ValueError("沒有資料可以做 profile")

        lowest, highest = float(prices.min()), float(prices.max())
        if lowest == highest:
            # 整段只有一個成交價：分布退化成一根柱子，硬分桶會讓邊界重疊
            return VolumeProfile(
                volume_by_price=pd.Series(
                    [float(volumes.sum())], index=[lowest], name="volume"
                ),
                value_area_fraction=self._value_area_fraction,
            )

        counts, edges = np.histogram(
            prices, bins=self._bucket_count, range=(lowest, highest), weights=volumes
        )
        # 用每個桶的中心價當索引，不用邊界：中心價才是那一桶代表的價位
        centres = (edges[:-1] + edges[1:]) / 2.0
        return VolumeProfile(
            volume_by_price=pd.Series(counts, index=centres, name="volume"),
            value_area_fraction=self._value_area_fraction,
        )
