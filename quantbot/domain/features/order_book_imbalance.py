# quantbot/domain/features/order_book_imbalance.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.depth_aggregation import DepthAggregation
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class OrderBookImbalance:
    """買賣兩側的掛量差多少，壓成 −1 到 +1 的一個數字。實作 domain 的 Feature。

        OBI = (買方掛量 − 賣方掛量) / (買方掛量 + 賣方掛量)

    分母是兩側的總量，所以它是**比例**而不是差額。這件事很重要：直接用差額的話，
    同樣「買方多掛 10 BTC」在總掛量 20 BTC 的市場與 2000 BTC 的市場是完全不同的
    事件，而差額看不出差別。除以總量之後，值域固定在 −1 到 +1，不同交易對、
    不同時段之間才可比。

    兩個極端有明確意義：+1 是賣方一張單都沒有，−1 是買方一張單都沒有。

    depth_level 與 aggregation 都進名字，因為它們是兩個不同的特徵而不是同一個特徵
    的設定：前 5 檔與前 20 檔測的是不同深度的壓力，平均與收盤取樣測的是不同時點。
    """

    def __init__(
        self,
        depth_level: int = 5,
        *,
        aggregation: DepthAggregation = DepthAggregation.MEAN,
    ) -> None:
        if depth_level not in DepthColumns.LEVELS:
            raise ValueError(
                f"沒有錄前 {depth_level} 檔。錄下來的深度是 {DepthColumns.LEVELS}，"
                "而這是 schema 的一部分——換一個深度要重新錄，不是重算"
            )
        self.depth_level = depth_level
        self.aggregation = aggregation

    @property
    def name(self) -> str:
        return f"obi_{self.depth_level}_{self.aggregation}"

    @property
    def warmup_bar_count(self) -> int:
        """不需要暖機：它是單一時點的橫斷面壓力，不含任何回看視窗。"""
        return 0

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES, MarketInput.DEPTH})

    def compute(self, view: MarketView) -> pd.Series:
        """算出每根 K 線的 OBI，index 與 K 線完全相同。

        沒有任何深度取樣的那幾根是 NaN，而那在這個特徵上是常態而不是例外：
        掛單簿只有「錄製程式活著的那段時間」才有資料，而 K 線有完整歷史。
        """
        aligned = self.aligned(view)
        return aligned.reindex(view.candles.open_times).rename(self.name)

    def aligned(self, view: MarketView) -> pd.Series:
        """先算比例、再按 K 線聚合。

        順序不能顛倒。先把兩側掛量平均起來、再算比例，算的是「這一分鐘的平均買方
        掛量對平均賣方掛量」，那是另一個量——比例的平均不等於平均的比例。兩種寫法
        都跑得出 −1 到 +1 的數字，也都畫得出圖，只有並排對數字才看得出差別。
        """
        depth = view.require_depth()
        timeframe = view.candles.instrument.timeframe
        resampled = self.ratio(depth.frame).resample(
            timeframe.pandas_frequency, label="left", closed="left"
        )
        return (
            resampled.mean()
            if self.aggregation is DepthAggregation.MEAN
            else resampled.last()
        )

    def ratio(self, depth: pd.DataFrame) -> pd.Series:
        """原始取樣頻率下的 OBI，不做任何聚合。

        驗證這個特徵有沒有預測力時要用這一個：它衰減得很快，先聚合到 K 線再驗，
        驗到的是「聚合之後還剩多少」，而不是這個特徵本身有多少。

        名字裡沒有 aggregation，因為這一層還沒有聚合。名字要說實話——
        叫它 obi_5_mean 會讓報告上兩個不同粒度的結果看起來像同一個東西。
        """
        bid = depth[DepthColumns.bid_quantity(self.depth_level)]
        ask = depth[DepthColumns.ask_quantity(self.depth_level)]
        total = bid + ask
        # 兩側都空的時候補 NaN 而不是 0：0 的意思是「兩側一樣多」，
        # 而「兩側都沒有掛單」是另一回事，那時候這個特徵沒有定義。
        return ((bid - ask) / total).where(total > 0).rename(f"obi_{self.depth_level}")


class OrderBookImbalanceBuilder:
    """設定檔的 obi。深度只能是錄過的那幾檔，聚合只能是 mean 或 last。"""

    @property
    def kind(self) -> str:
        return "obi"

    def build(self, parameters: FeatureParameters) -> OrderBookImbalance:
        aggregation = parameters.text("aggregation", DepthAggregation.MEAN.value)
        if aggregation not in tuple(DepthAggregation):
            raise ValueError(
                f"aggregation 只能是 {[value.value for value in DepthAggregation]}，"
                f"實得 {aggregation!r}"
            )
        return OrderBookImbalance(
            parameters.integer("depth_level", DepthColumns.LEVELS[0]),
            aggregation=DepthAggregation(aggregation),
        )
