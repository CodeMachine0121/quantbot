# quantbot/application/search_combinations_application.py
from __future__ import annotations

import pandas as pd

from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.domain.dto.search_report import SearchReportDto, SearchTrialDto
from quantbot.domain.services.backtest_service import BacktestService
from quantbot.domain.services.performance_metrics_service import (
    PerformanceMetricsService,
)
from quantbot.domain.services.return_shuffle_service import ReturnShuffleService
from quantbot.domain.services.search_space_service import SearchSpaceService
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.services.trial_deflation_service import TrialDeflationService
from quantbot.domain.services.walk_forward_service import (
    WalkForwardFold,
    WalkForwardService,
)
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.backtest_specification import BacktestSpecification
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.search_space import SearchSpace
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange


class SearchCombinationsApplication:
    """跑一整個搜尋空間，並且把「這個結果值不值得看」一起算出來。

    它讀資料**一次**，然後在同一張表上跑幾百個策略。這是 Day 19 把
    `RunBacktestApplication.evaluate()` 跟 `run()` 分開的理由：前者不碰資料庫。

    同一份程式碼也負責在打亂順序的假資料上跑一次同樣的搜尋。兩次搜尋要走完全相同
    的路徑（同樣的特徵算法、同樣的引擎、同樣的成本、同樣的切分），否則比較就不成立
    ——所以打亂那條路只換掉最前面的 K 線，後面一個字都不改。
    """

    def __init__(
        self,
        *,
        features: ComputeFeaturesApplication,
        assembly: StrategyAssemblyService,
        engine: StrategyEngine,
        backtest: BacktestService,
        space: SearchSpaceService,
        walk_forward: WalkForwardService,
        metrics: PerformanceMetricsService,
        deflation: TrialDeflationService,
        shuffle: ReturnShuffleService,
    ) -> None:
        self._features = features
        self._assembly = assembly
        self._engine = engine
        self._backtest = backtest
        self._space = space
        self._walk_forward = walk_forward
        self._metrics = metrics
        self._deflation = deflation
        self._shuffle = shuffle

    async def load_view(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
    ) -> MarketView:
        return await self._features.load_view(
            instrument, period, specifications=specification.features
        )

    def table_for(
        self,
        view: MarketView,
        specifications: tuple[StrategySpecification, ...],
    ) -> pd.DataFrame:
        """所有組合共用的一張表：把每一份設定要的特徵取聯集，一次算完。

        兩個理由，第二個比第一個重要：

        1. **省時間。** 48 個組合裡 `ema_21` 出現很多次，算一次就好。
        2. **公平。** 一張共用的表意味著所有組合看到的是**同一段資料**，包含
           同一段暖機期。分開算的話，用 `ema_55` 的組合會比用 `ema_8` 的少掉
           幾十根開頭資料，而兩者的夏普就不再可以並排比較——一個在「資料比較少
           但可能剛好避開一段爛行情」的區間上算出來的夏普，跟別人不是同一件事。

        去重用 describe() 當鍵，跟 Day 18 的交叉組合同一個做法。
        """
        merged: dict[str, FeatureSpecification] = {}
        for specification in specifications:
            for feature in specification.features:
                merged.setdefault(feature.describe(), feature)
        features = self._features.compute_from_view(
            view, specifications=tuple(merged.values())
        )
        return view.strategy_table(features)

    def shuffled_view(self, view: MarketView, *, seed: int) -> MarketView:
        """同一份原料，只把 K 線換成打亂重建的版本。"""
        return MarketView(
            candles=self._shuffle.shuffled_candles(view.candles, seed=seed),
            trades=view.trades,
            depth=view.depth,
        )

    def search(
        self,
        space: SearchSpace,
        view: MarketView,
        *,
        label: str,
        backtest_specification: BacktestSpecification,
        periods_per_year: float,
        in_sample_fraction: float = 0.7,
    ) -> SearchReportDto:
        """在一張已經算好的表上跑完整個搜尋空間。

        切分只做一次，而且**在跑任何組合之前**。順序反過來（先跑完再切）會讓
        「用樣本外挑策略」變成一件很容易不小心做到的事，而那跟沒有樣本外一樣。
        """
        specifications = self._space.expand(space)
        table = self.table_for(view, specifications)
        fold = self._walk_forward.split(
            pd.DatetimeIndex(table.index), in_sample_fraction=in_sample_fraction
        )

        trials = tuple(
            self._trial(
                specification,
                table,
                fold=fold,
                backtest_specification=backtest_specification,
                periods_per_year=periods_per_year,
            )
            for specification in specifications
        )
        return SearchReportDto(
            label=label,
            trial_count=len(specifications),
            pruned_count=space.unconstrained_combination_count - len(specifications),
            unconstrained_combination_count=space.unconstrained_combination_count,
            in_sample_bar_count=len(fold.in_sample),
            out_of_sample_bar_count=len(fold.out_of_sample),
            periods_per_year=periods_per_year,
            expected_maximum_sharpe=self._deflation.expected_maximum_sharpe(
                trial_count=len(specifications),
                observation_count=len(fold.in_sample),
                periods_per_year=periods_per_year,
            ),
            trials=trials,
        )

    def _trial(
        self,
        specification: StrategySpecification,
        table: pd.DataFrame,
        *,
        fold: WalkForwardFold,
        backtest_specification: BacktestSpecification,
        periods_per_year: float,
    ) -> SearchTrialDto:
        """一個組合的樣本內與樣本外各回測一次。

        兩段**分別**回測，而不是回測整段再把權益曲線切開。後者的樣本外報酬會從
        樣本內結束時的權益開始算，於是一個樣本內大賺的組合會在樣本外拿到一個
        被放大的絕對金額——而要比較的是報酬率，不是金額。
        """
        strategy = self._assembly.assemble(specification)
        in_sample = self._backtest.run(
            self._engine.signals(strategy, table.loc[fold.in_sample]),
            backtest_specification,
        )
        out_of_sample = self._backtest.run(
            self._engine.signals(strategy, table.loc[fold.out_of_sample]),
            backtest_specification,
        )
        return SearchTrialDto(
            strategy_name=specification.name,
            trade_count=in_sample.trade_count,
            in_sample_sharpe=self._metrics.sharpe_ratio(
                in_sample.returns, periods_per_year=periods_per_year
            ),
            in_sample_return=in_sample.total_return,
            out_of_sample_sharpe=self._metrics.sharpe_ratio(
                out_of_sample.returns, periods_per_year=periods_per_year
            ),
            out_of_sample_return=out_of_sample.total_return,
        )
