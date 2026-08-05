# quantbot/domain/values/volume_profile.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolumeProfile:
    """價格軸上的成交量分布，以及從它推導出的幾個關鍵價位。

    它跟前面所有特徵最大的不同是**它不是時間序列**。索引是價格（分桶之後的價格
    區間），值是那個價位上總共成交了多少。所以它 NEVER 實作 Feature 協定——
    Feature 的契約是「回傳一條與 K 線等長、index 相同的序列」，而這個東西的
    index 是價格。

    能進特徵管線的是**從它算出來的純量**（距離 POC 多遠、在不在價值區間裡），
    那是 Day 15 要處理的事。這個區分不是形式主義：一張分布沒辦法跟 K 線對齊，
    硬要塞進管線只會產生一張全是 NaN 的表。
    """

    volume_by_price: pd.Series
    value_area_fraction: float

    def __post_init__(self) -> None:
        if not 0.0 < self.value_area_fraction <= 1.0:
            raise ValueError(
                f"value_area_fraction 必須落在 (0, 1]，收到 {self.value_area_fraction}"
            )

    @property
    def point_of_control(self) -> float:
        """成交量最大的那個價位（POC）。

        它是「多數人的成本」最直接的近似：那個價格上換手最多，所以在那裡進場的人
        最多。價格回到 POC 附近時，那群人面對的是損益兩平，而那會影響他們的行為。
        """
        return float(self.volume_by_price.idxmax())

    @property
    def total_volume(self) -> float:
        return float(self.volume_by_price.sum())

    @property
    def value_area(self) -> tuple[float, float]:
        """價值區間：從 POC 往兩側擴張，直到涵蓋 value_area_fraction 的成交量。

        擴張規則是每一步選「相鄰兩側裡成交量較大的那一格」。這是這個指標的傳統
        算法，而它有一個要知道的性質：**結果不一定對稱**，也不保證是全域最窄的
        區間。它是一個貪婪演算法，不是最佳化。

        用貪婪而不是「找最窄的區間」是刻意的：前者是業界通用的定義，換一個軟體
        算出來的數字對得起來；後者更「正確」但沒有人用，對不上任何人的圖。
        """
        volumes = self.volume_by_price.to_numpy(dtype="float64")
        prices = self.volume_by_price.index.to_numpy(dtype="float64")
        target = self.total_volume * self.value_area_fraction

        peak = int(np.argmax(volumes))
        lower, upper = peak, peak
        accumulated = volumes[peak]

        while accumulated < target and (lower > 0 or upper < len(volumes) - 1):
            below = volumes[lower - 1] if lower > 0 else -1.0
            above = volumes[upper + 1] if upper < len(volumes) - 1 else -1.0
            if above >= below:
                upper += 1
                accumulated += volumes[upper]
            else:
                lower -= 1
                accumulated += volumes[lower]

        return float(prices[lower]), float(prices[upper])

    def key_levels(self) -> dict[str, float]:
        """報告與圖表要的那幾個數字。"""
        low, high = self.value_area
        return {
            "point_of_control": self.point_of_control,
            "value_area_low": low,
            "value_area_high": high,
        }
