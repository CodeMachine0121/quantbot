# quantbot/application/compute_features_application.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.features.feature_pipeline import FeaturePipeline
from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.interfaces.depth_repository import DepthRepository
from quantbot.domain.interfaces.trade_repository import TradeRepository
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.time_range import TimeRange


class ComputeFeaturesApplication:
    """一份設定 ＋ 一段時間 → 一張特徵表。

    它做的第一件事是**先建管線、再讀資料**。順序反過來（先把三種資料都撈出來）
    也能跑，但那會讀進根本不會用到的東西：一份只有 ema 與 rsi 的設定不需要
    七十幾萬列的逐筆成交，而讀那些要花好幾秒。

    管線建好之後 required_inputs 就問得出來，所以要讀什麼是算得出來的。
    這是 Day 10 把 required_inputs 放進 Feature 協定的實際回報。
    """

    def __init__(
        self,
        *,
        candles: CandleRepository,
        trades: TradeRepository,
        depth: DepthRepository,
        registry: FeatureRegistry,
    ) -> None:
        self._candles = candles
        self._trades = trades
        self._depth = depth
        self._registry = registry

    async def run(
        self,
        instrument: Instrument,
        period: TimeRange,
        *,
        specifications: tuple[FeatureSpecification, ...],
        trim_warmup: bool = True,
    ) -> pd.DataFrame:
        pipeline = FeaturePipeline(self._registry.build_all(specifications))
        view = await self._load(instrument, period, pipeline.required_inputs)
        return pipeline.trimmed(view) if trim_warmup else pipeline.compute(view)

    async def run_with_view(
        self,
        instrument: Instrument,
        period: TimeRange,
        *,
        specifications: tuple[FeatureSpecification, ...],
        trim_warmup: bool = True,
    ) -> tuple[pd.DataFrame, MarketView]:
        """特徵表與它算的那份原料一起交出去，只讀一次資料庫。

        Day 17 之後的策略路徑需要兩邊：條件要讀特徵，也要讀 K 線的收盤價。
        分兩次呼叫 run() 與 load_view() 會讀兩次同一段資料，而那是幾秒的事。
        """
        pipeline = FeaturePipeline(self._registry.build_all(specifications))
        view = await self._load(instrument, period, pipeline.required_inputs)
        table = pipeline.trimmed(view) if trim_warmup else pipeline.compute(view)
        return table, view

    def compute_from_view(
        self,
        view: MarketView,
        *,
        specifications: tuple[FeatureSpecification, ...],
        trim_warmup: bool = True,
    ) -> pd.DataFrame:
        """原料已經在手上時算特徵，不讀資料庫。

        Day 21 的隨機資料示範要用它：那條路徑的 K 線是把真實報酬打亂之後重建的，
        資料庫裡不存在，但特徵要用完全一樣的算法算出來才比較得公平。
        """
        pipeline = FeaturePipeline(self._registry.build_all(specifications))
        return pipeline.trimmed(view) if trim_warmup else pipeline.compute(view)

    async def load_view(
        self,
        instrument: Instrument,
        period: TimeRange,
        *,
        specifications: tuple[FeatureSpecification, ...],
    ) -> MarketView:
        """給報告與圖表用：拿到跟 run() 完全一樣的那份原料。"""
        pipeline = FeaturePipeline(self._registry.build_all(specifications))
        return await self._load(instrument, period, pipeline.required_inputs)

    async def _load(
        self,
        instrument: Instrument,
        period: TimeRange,
        required: frozenset[MarketInput],
    ) -> MarketView:
        """只讀真的會用到的那幾種資料。"""
        listing = Listing.of(instrument)
        return MarketView(
            candles=await self._candles.read(instrument, period),
            trades=(
                await self._trades.read(listing, period)
                if MarketInput.TRADES in required
                else None
            ),
            depth=(
                await self._depth.read(listing, period)
                if MarketInput.DEPTH in required
                else None
            ),
        )
