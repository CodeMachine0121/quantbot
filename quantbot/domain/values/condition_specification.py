# quantbot/domain/values/condition_specification.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from quantbot.domain.values.feature_parameters import FeatureParameters, ParameterValue


@dataclass(frozen=True)
class ConditionSpecification:
    """設定檔裡的一個條件節點。有 children 就是組合節點，沒有就是葉節點。

    這是 Day 15 的 FeatureSpecification 多長一個 children 之後的樣子，多的那一個
    欄位就是條件與特徵的全部差別：特徵是一個平的清單，條件是一棵樹。

    參數的型別檢查沿用 FeatureParameters，不另寫一份。那個類別的名字講的是它的
    出身，做的事其實是「設定檔的一組弱型別參數」——轉型、預設值、以及 ensure_used()
    抓拼錯的欄名。條件面對的是同一個問題，所以沿用它比複製一份好：驗證邏輯有兩份的
    時候，修好其中一份的下場是另一份繼續錯。

    跟 FeatureSpecification 一樣，這裡刻意不驗證參數的值。這個值只忠實記下使用者
    說了什麼，「這個 kind 需要哪些參數」的知識在各自的 builder 手上。
    """

    kind: str
    parameters: Mapping[str, ParameterValue] = FeatureParameters.EMPTY
    children: tuple[ConditionSpecification, ...] = field(default_factory=tuple)

    def to_parameters(self) -> FeatureParameters:
        return FeatureParameters(values=self.parameters)

    def describe(self) -> str:
        """給錯誤訊息用的一行。組合節點會遞迴展開，所以指得出是樹裡的哪一個節點。"""
        described = self.kind
        if self.parameters:
            joined = ", ".join(
                f"{key}={value}" for key, value in sorted(self.parameters.items())
            )
            described = f"{described}({joined})"
        if self.children:
            inner = ", ".join(child.describe() for child in self.children)
            described = f"{described}[{inner}]"
        return described
