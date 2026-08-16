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

    def with_exit_from(self, donor: StrategySpecification) -> StrategySpecification:
        """自己的進場與過濾，配另一份設定的出場。

        這是積木化真正要換到的東西：兩個獨立寫出來的策略，可以把其中一半換掉而
        不必改任何 Python。如果這件事做不到，那麼「策略是積木」只是一種說法。

        **時間規則跟著出場走。** 最大持有根數是「等不到出場條件時的後備出場」，
        冷卻期是「出場之後多久才准再進」——兩者都是出場側的規則，所以捐出出場
        條件的那一份也把它們一起捐出來。留著自己的會得到一個沒人要的組合：
        新的出場條件配舊的持有上限。

        特徵清單取聯集並去重，因為兩邊的條件都要有東西可讀。去重用 describe()
        的字串當鍵，那是「同一種特徵、同一組參數」的可讀形式。
        """
        merged: dict[str, FeatureSpecification] = {}
        for specification in (*self.features, *donor.features):
            merged.setdefault(specification.describe(), specification)
        return StrategySpecification(
            name=f"{self.name}_entry_x_{donor.name}_exit",
            features=tuple(merged.values()),
            entry=self.entry,
            exit=donor.exit,
            filters=self.filters,
            holding=donor.holding,
            direction=self.direction,
        )
