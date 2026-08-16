# quantbot/domain/strategies/strategy.py
from __future__ import annotations

from dataclasses import dataclass, field

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.strategies.constant_condition import Always, Never
from quantbot.domain.values.holding_rules import HoldingRules
from quantbot.domain.values.position_direction import PositionDirection


@dataclass(frozen=True)
class Strategy:
    """一個策略：三組條件加上兩條時間規則，沒有別的。

    三組條件的角色**不能互換**，這是今天最重要的一個界線：

    - entry 說「可以進場了」。
    - exit 說「該離場了」。
    - filters 說「別進」——它只否決進場，NEVER 促成進場，也 NEVER 促成出場。

    把過濾條件跟進場條件混成一組會壞在什麼地方：「只在活躍時段交易」寫成進場條件
    的一部分，那麼一個在活躍時段進場、在冷清時段還抱著的部位，會因為「活躍度掉了」
    而被算成不該持有。過濾管的是新部位，不是手上的部位。exit 才管手上的部位。

    為什麼策略是一份資料而不是一個 class：一個策略如果是一個類別，三個策略就有
    三份重複的「算特徵、判斷條件、決定部位」邏輯，而且想試「這個策略的進場條件
    配那個策略的出場條件」時完全沒辦法——那要求兩個類別內部的一段邏輯可以拆出來
    交換，而類別沒有留下那個縫。條件樹有。
    """

    name: str
    entry: Condition
    exit: Condition
    filters: Condition = field(default_factory=Always)
    holding: HoldingRules = field(default_factory=HoldingRules.unbounded)
    direction: PositionDirection = PositionDirection.LONG

    @classmethod
    def buy_and_hold(cls, name: str = "buy_and_hold") -> Strategy:
        """基準策略：第一根就進場，然後什麼都不做。

        它值得是每一份報告的第一列。任何組合出來的策略如果贏不過它，那些條件
        就只是在製造手續費——而這件事在只看「總報酬率 +38%」的時候看不出來。
        """
        return cls(name=name, entry=Always(), exit=Never())

    @property
    def required_features(self) -> frozenset[str]:
        """三棵樹要的欄位的聯集。使用者不必宣告，也就不會漏。"""
        return (
            self.entry.required_features
            | self.exit.required_features
            | self.filters.required_features
        )

    @property
    def warmup_bar_count(self) -> int:
        """三棵樹裡最保守的那一個。特徵自己的暖機期不算在這裡。"""
        return max(
            self.entry.warmup_bar_count,
            self.exit.warmup_bar_count,
            self.filters.warmup_bar_count,
        )

    def describe(self) -> str:
        """一份可讀的策略全文。設定檔載入後印它，就能核對讀進來的是不是原意。"""
        lines = [
            f"策略 {self.name}（{self.direction}）",
            f"  進場  {self.entry.describe()}",
            f"  出場  {self.exit.describe()}",
            f"  過濾  {self.filters.describe()}",
            f"  持有  {self.holding.describe()}",
            f"  需要特徵  {sorted(self.required_features)}",
        ]
        return "\n".join(lines)
