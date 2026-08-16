# quantbot/domain/strategies/condition_registry.py
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from quantbot.domain.interfaces.condition_builder import ConditionBuilder
from quantbot.domain.strategies.condition import (
    AllOfBuilder,
    AnyOfBuilder,
    Condition,
    NotBuilder,
)
from quantbot.domain.strategies.constant_condition import AlwaysBuilder, NeverBuilder
from quantbot.domain.strategies.crossover_condition import CrossoverBuilder
from quantbot.domain.strategies.event_condition import EventBuilder
from quantbot.domain.strategies.feature_comparison_condition import (
    FeatureComparisonBuilder,
)
from quantbot.domain.strategies.range_condition import RangeBuilder
from quantbot.domain.strategies.sustained_condition import SustainedBuilder
from quantbot.domain.strategies.threshold_condition import ThresholdBuilder
from quantbot.domain.values.condition_specification import ConditionSpecification


class ConditionRegistry:
    """字串 → 條件。Day 15 那張特徵註冊表的條件版。

    兩個地方跟特徵不一樣。

    第一，它是**遞迴**的：組合節點的子節點也是設定，所以要先把子節點建好才建得出
    這一層。遞迴放在註冊表而不是每個 builder 裡，因為「子節點怎麼來」是註冊表的
    知識——builder 只該處理自己這一層。

    第二，它要防無限深度。一份手寫的 YAML 不會巢到一百層，但一份**程式產生的**
    設定檔會（Day 21 的組合搜尋就會產生設定檔），而 Python 的遞迴上限一到就是
    RecursionError，那個訊息對使用者毫無意義。所以深度上限是自己的，錯誤訊息
    講得出是哪一份設定太深。
    """

    MAXIMUM_DEPTH: ClassVar[int] = 12

    BUILDERS: ClassVar[Mapping[str, ConditionBuilder]] = MappingProxyType(
        {
            builder.kind: builder
            for builder in (
                ThresholdBuilder(),
                FeatureComparisonBuilder(),
                CrossoverBuilder(),
                RangeBuilder(),
                EventBuilder(),
                AlwaysBuilder(),
                NeverBuilder(),
                AllOfBuilder(),
                AnyOfBuilder(),
                NotBuilder(),
                SustainedBuilder(),
            )
        }
    )

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self.BUILDERS))

    def build(self, specification: ConditionSpecification) -> Condition:
        """一棵設定樹變成一棵條件樹。任何一個節點有問題就整棵失敗。"""
        return self._build(specification, depth=1)

    def _build(self, specification: ConditionSpecification, *, depth: int) -> Condition:
        if depth > self.MAXIMUM_DEPTH:
            raise ValueError(
                f"條件樹太深（超過 {self.MAXIMUM_DEPTH} 層）：{specification.kind}"
            )
        if specification.kind not in self.BUILDERS:
            raise ValueError(
                f"未知的條件 {specification.kind!r}（可用：{list(self.kinds())}）"
            )

        children = tuple(
            self._build(child, depth=depth + 1) for child in specification.children
        )
        parameters = specification.to_parameters()
        try:
            condition = self.BUILDERS[specification.kind].build(parameters, children)
            parameters.ensure_used()
        except ValueError as error:
            raise ValueError(f"{specification.describe()}：{error}") from error
        return condition
