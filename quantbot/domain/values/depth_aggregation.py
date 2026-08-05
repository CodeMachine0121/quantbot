# quantbot/domain/values/depth_aggregation.py
from enum import StrEnum


class DepthAggregation(StrEnum):
    """掛單簿的不規則取樣要怎麼壓成一根 K 線一個值。

    這不是可有可無的選項。深度摘要是每秒一筆，一根 1 分鐘 K 線裡有 60 筆，
    而「這一分鐘的掛單不對稱」有兩種都說得通的定義：

    - MEAN：整根期間的平均壓力。它比較穩，但會把一次劇烈的瞬間擠壓抹平。
    - LAST：收盤那一刻的壓力。它跟「訊號在收盤時產生」這件事對得起來，
      但只採樣一個瞬間，而掛單簿一秒可以變好幾次。

    兩者算出來的數字差很多，所以它進了特徵的名字（obi_5_mean 與 obi_5_last 是
    兩個不同的特徵），NEVER 讓兩個定義共用一個名字。
    """

    MEAN = "mean"
    LAST = "last"
