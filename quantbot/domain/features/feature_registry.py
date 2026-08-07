# quantbot/domain/features/feature_registry.py
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from quantbot.domain.features.average_true_range import ATRBuilder
from quantbot.domain.features.breakout import BreakoutBuilder
from quantbot.domain.features.candle_indicator_feature import CandleIndicatorBuilder
from quantbot.domain.features.distance_to_point_of_control import (
    DistanceToPointOfControlBuilder,
)
from quantbot.domain.features.liquidity_swing import LiquiditySwingBuilder
from quantbot.domain.features.order_book_imbalance import OrderBookImbalanceBuilder
from quantbot.domain.features.prior_extreme import PriorExtremeBuilder
from quantbot.domain.features.trading_activity import TradingActivityBuilder
from quantbot.domain.features.volume_weighted_average_price import VWAPBuilder
from quantbot.domain.features.vwap_deviation import VWAPDeviationBuilder
from quantbot.domain.interfaces.feature import Feature
from quantbot.domain.interfaces.feature_builder import FeatureBuilder
from quantbot.domain.values.feature_specification import FeatureSpecification


def _by_kind(*builders: FeatureBuilder) -> Mapping[str, FeatureBuilder]:
    """用每個 builder 自己宣告的 kind 當鍵，而不是在這裡手寫字串。

    手寫的話會有兩份真相：builder 裡的 kind 與這張表的鍵。它們一旦不一致，
    錯誤訊息會指向一個註冊表裡不存在的名字。
    """
    registered: dict[str, FeatureBuilder] = {}
    for builder in builders:
        if builder.kind in registered:
            raise ValueError(f"重複註冊的 kind：{builder.kind}")
        registered[builder.kind] = builder
    return MappingProxyType(registered)


class FeatureRegistry:
    """字串 → 特徵。Day 06 那張 INDICATORS 的完整版。

    Day 06 的註冊表放的是**類別**，取出來之後 `cls(period)` 就能用，因為三個指標的
    參數形狀完全一樣。到今天為止有十種特徵，參數從 period 一個到「side ＋ window ＋
    bucket_count」都有，而 `cls(**parameters)` 那種寫法是反射式分派——型別檢查器
    看不到，參數名一改就在執行期才炸。所以中間多一層 builder。

    這張表就是 Day 16 策略積木庫的原料來源：使用者在 YAML 裡寫 `obi`，
    引擎在這裡查到 builder，builder 負責把參數變成物件並在參數不合法時報錯。
    使用者因此完全不必碰 Python。
    """

    BUILDERS: ClassVar[Mapping[str, FeatureBuilder]] = _by_kind(
        CandleIndicatorBuilder("sma"),
        CandleIndicatorBuilder("ema"),
        CandleIndicatorBuilder("rsi"),
        ATRBuilder(),
        VWAPBuilder(),
        VWAPDeviationBuilder(),
        TradingActivityBuilder(),
        OrderBookImbalanceBuilder(),
        PriorExtremeBuilder(),
        BreakoutBuilder(),
        LiquiditySwingBuilder(),
        DistanceToPointOfControlBuilder(),
    )

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self.BUILDERS))

    def build(self, specification: FeatureSpecification) -> Feature:
        """一行設定變成一個特徵物件。

        參數驗證分兩段，兩段都在這裡完成，所以呼叫端拿到的物件一定是合法的：
        builder 負責「這個值合不合法」，ensure_used() 負責「有沒有多給不認識的參數」。
        後者抓的是拼錯的欄名，而那是設定檔最常見的錯誤。
        """
        if specification.kind not in self.BUILDERS:
            raise ValueError(
                f"未知的特徵 {specification.kind!r}（可用：{list(self.kinds())}）"
            )
        parameters = specification.to_parameters()
        feature = self.BUILDERS[specification.kind].build(parameters)
        parameters.ensure_used()
        return feature

    def build_all(
        self, specifications: tuple[FeatureSpecification, ...]
    ) -> tuple[Feature, ...]:
        """整份設定一次建完。**任何一行有問題就整份失敗**，不做部分成功。

        理由是「算出一半的特徵」沒有用：策略要的是完整的一組。與其讓呼叫端拿著
        一個殘缺的清單再去判斷，不如在這裡就失敗，而錯誤訊息指名是哪一行。
        """
        built: list[Feature] = []
        for specification in specifications:
            try:
                built.append(self.build(specification))
            except ValueError as error:
                raise ValueError(f"{specification.describe()}：{error}") from error
        return tuple(built)
