# quantbot/application/generate_signals_application.py
from __future__ import annotations

import pandas as pd

from quantbot.application.compute_features_application import ComputeFeaturesApplication
from quantbot.domain.services.strategy_assembly_service import StrategyAssemblyService
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.strategies.strategy_engine import StrategyEngine
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.strategy_signals import StrategySignals
from quantbot.domain.values.strategy_specification import StrategySpecification
from quantbot.domain.values.time_range import TimeRange


class GenerateSignalsApplication:
    """一份策略設定 ＋ 一段時間 → 一組訊號與部位。

    它做的第一件事是**先組裝策略，再讀資料**，跟 Day 15 的特徵管線同一個順序。
    組裝會做參數驗證與特徵對帳，那些錯誤不必等到讀完幾萬列資料才報出來。

    它重用 ComputeFeaturesApplication 而不是自己撈資料。用例呼叫用例在這裡是對的：
    「一份設定 → 一張特徵表」已經是一個完整的用例，包含只讀真的會用到的那幾種
    原料那段判斷。再寫一份的話，Day 15 修好的東西這裡會再錯一次。
    """

    def __init__(
        self,
        *,
        features: ComputeFeaturesApplication,
        assembly: StrategyAssemblyService,
        engine: StrategyEngine,
    ) -> None:
        self._features = features
        self._assembly = assembly
        self._engine = engine

    async def run(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
    ) -> StrategySignals:
        strategy = self._assembly.assemble(specification)
        table = await self.load_table(specification, instrument, period)
        return self._engine.signals(strategy, table)

    async def run_assembled(
        self,
        strategy: Strategy,
        table: pd.DataFrame,
    ) -> StrategySignals:
        """資料已經在手上時的入口。Day 21 的組合搜尋會用它——幾百個策略共用
        同一張表，讀一次就好。"""
        return self._engine.signals(strategy, table)

    async def load_table(
        self,
        specification: StrategySpecification,
        instrument: Instrument,
        period: TimeRange,
    ) -> pd.DataFrame:
        """條件要吃的那張表：K 線的欄位 ＋ 這份設定宣告的特徵。

        兩者併在一起是刻意的。價格不是特徵——它是原料——但條件要拿收盤價跟 VWAP
        比大小，所以它必須在同一張表裡，而且用 `close` 這個名字，不是某個
        假特徵的名字。

        對齊方向是「K 線對齊到特徵表」：特徵表已經切掉暖機期，所以它比 K 線短，
        而反過來對齊會把暖機期的 NaN 放回來。
        """
        features, view = await self._features.run_with_view(
            instrument, period, specifications=specification.features
        )
        candles = view.candles.frame.reindex(features.index)
        return pd.concat([candles, features], axis=1)
