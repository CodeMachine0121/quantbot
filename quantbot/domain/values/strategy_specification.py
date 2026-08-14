# quantbot/domain/values/strategy_specification.py
from __future__ import annotations

from dataclasses import dataclass, field

from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.holding_rules import HoldingRules
from quantbot.domain.values.position_direction import PositionDirection


@dataclass(frozen=True)
class StrategySpecification:
    """一份策略設定檔讀進來的樣子。它跟 Strategy 差在還沒建成物件。

    為什麼多這一層而不是讓載入器直接吐 Strategy：載入器住在 infrastructure，
    而「哪個字串對應哪個條件類別」的知識屬於 domain。中間放一個值，YAML 的格式
    知識與條件的組裝知識就各自留在該待的地方，兩邊都能單獨測。

    features 是這份策略要算哪些特徵。它跟條件樹裡引用的名字**必須對得起來**，
    而那個對帳由 StrategyAssemblyService 在組裝時做——設定檔寫錯的東西要在啟動時
    就報錯，NEVER 等到跑完一輪回測才發現某個條件從來沒成立過。
    """

    name: str
    features: tuple[FeatureSpecification, ...]
    entry: ConditionSpecification
    exit: ConditionSpecification
    filters: ConditionSpecification | None = None
    holding: HoldingRules = field(default_factory=HoldingRules.unbounded)
    direction: PositionDirection = PositionDirection.LONG
