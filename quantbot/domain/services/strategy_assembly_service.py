# quantbot/domain/services/strategy_assembly_service.py
from __future__ import annotations

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.strategies.condition_registry import ConditionRegistry
from quantbot.domain.strategies.constant_condition import Always
from quantbot.domain.strategies.strategy import Strategy
from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.strategy_specification import StrategySpecification


class StrategyAssemblyService:
    """一份設定變成一個可以跑的策略，順便把設定檔最容易出的那個錯擋掉。

    組裝本身沒什麼——三棵樹各建一次。真正的價值在**對帳**：條件樹引用的每一個
    欄名，都必須來自這份設定宣告的特徵，或者是 K 線本來就有的欄位。少了這道檢查，
    一個把 `ema_12` 寫成 `ema12` 的設定檔會照樣載入、照樣跑完、照樣產出一份報告，
    而那個條件從第一根到最後一根都不成立——回測結果會是「這個策略沒有任何交易」，
    看起來像策略太保守，實際上是打錯一個字。

    這件事屬於 domain service 而不是註冊表，因為它跨越兩個註冊表：要知道特徵會
    產出什麼名字（FeatureRegistry），也要知道條件要讀什麼名字（ConditionRegistry）。
    兩邊都不該認識對方。

    它是 domain service，所以不吃任何 Protocol、不做 I/O，兩個註冊表都是具體實例。
    """

    def __init__(
        self,
        *,
        features: FeatureRegistry,
        conditions: ConditionRegistry,
    ) -> None:
        self._features = features
        self._conditions = conditions

    def assemble(self, specification: StrategySpecification) -> Strategy:
        strategy = Strategy(
            name=specification.name,
            entry=self._conditions.build(specification.entry),
            exit=self._conditions.build(specification.exit),
            filters=(
                self._conditions.build(specification.filters)
                if specification.filters is not None
                else Always()
            ),
            holding=specification.holding,
            direction=specification.direction,
        )
        self._ensure_features_declared(specification, strategy)
        return strategy

    def available_columns(self, specification: StrategySpecification) -> frozenset[str]:
        """這份設定跑起來之後，特徵表會有哪些欄名。

        兩個來源：宣告的特徵各自的 name，加上 K 線本來的欄位。後者不是特徵——
        它是原料，而條件要拿收盤價跟 VWAP 比大小，所以它必須在表裡。
        """
        built = self._features.build_all(specification.features)
        return frozenset(feature.name for feature in built) | frozenset(
            CandleColumns.all_columns()
        )

    def _ensure_features_declared(
        self, specification: StrategySpecification, strategy: Strategy
    ) -> None:
        available = self.available_columns(specification)
        missing = sorted(strategy.required_features - available)
        if missing:
            raise ValueError(
                f"策略 {specification.name} 的條件引用了沒有宣告的欄位：{missing}"
                f"（這份設定會產出：{sorted(available)}）"
            )
