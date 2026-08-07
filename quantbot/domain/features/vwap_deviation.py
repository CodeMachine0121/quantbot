# quantbot/domain/features/vwap_deviation.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.features.volume_weighted_average_price import VWAP, VWAPBuilder
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class VWAPDeviation:
    """價格偏離 VWAP 幾個加權標準差。實作 domain 的 Feature。

        偏離 = (價格 − VWAP) / 加權標準差

    這是策略真正會用到的那個數字，而不是 VWAP 本身。理由是 VWAP 的單位是價格：
    「價格比 VWAP 高 120 USDT」在 BTC 上是小事，在 ETH 上是大事，而同一個門檻
    NEVER 能同時適用於兩個交易對。除以標準差之後它變成無單位的，跨交易對、
    跨時段才可比。

    這也是 Day 18 均值回歸策略裡「價格顯著偏離 VWAP」那句話的實際定義——
    「顯著」是幾個標準差，是一個要被寫下來的數字，不是一種感覺。
    """

    def __init__(self, vwap: VWAP) -> None:
        self._vwap = vwap

    @property
    def name(self) -> str:
        return f"{self._vwap.name}_deviation"

    @property
    def warmup_bar_count(self) -> int:
        """跟它包住的那個 VWAP 一樣。標準差不需要額外的視窗。"""
        return self._vwap.warmup_bar_count

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return self._vwap.required_inputs

    def compute(self, view: MarketView) -> pd.Series:
        price = self._vwap.price_source.of(view.candles.frame)
        centre = self._vwap.compute(view)
        spread = self._vwap.standard_deviation(view)
        # 標準差為 0 的時候（整段只有一個成交價）偏離沒有定義，回 NaN 而不是 inf
        return ((price - centre) / spread.where(spread > 0)).rename(self.name)


class VWAPDeviationBuilder:
    """設定檔的 vwap_deviation。它包住一個 VWAP，所以參數跟 vwap 完全一樣。"""

    @property
    def kind(self) -> str:
        return "vwap_deviation"

    def build(self, parameters: FeatureParameters) -> VWAPDeviation:
        return VWAPDeviation(VWAPBuilder().build(parameters))
