# quantbot/domain/services/search_space_service.py
from __future__ import annotations

from dataclasses import replace
from itertools import product

from quantbot.domain.features.feature_registry import FeatureRegistry
from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.feature_parameters import ParameterValue
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.search_space import (
    ConditionParameterAxis,
    ConditionTree,
    FeatureParameterAxis,
    IncreasingPeriodConstraint,
    SearchAxis,
    SearchSpace,
)
from quantbot.domain.values.strategy_specification import StrategySpecification


class SearchSpaceService:
    """一個搜尋空間展開成一堆策略設定。

    它做三件事，而第二件是唯一不明顯的那個：

    1. **笛卡兒積。** 各軸的值排列組合，數量是各軸長度的乘積。
    2. **名字改寫。** 改了特徵參數就改了特徵的名字（`ema_12` → `ema_8`），
       而條件樹引用的是名字。所以每產生一個組合，都要把條件裡引用舊名字的地方
       換成新名字，否則展開出來的設定會在 Day 17 的對帳那一關全部失敗。
    3. **剪枝。** 講不通的組合直接不產生（例如快線週期比慢線長），而剪掉幾個
       要記錄下來——沒有記錄的剪枝等於偷偷縮小搜尋空間。

    第二件事是「參數與名字綁在一起」這個設計的代價。特徵的名字帶參數（`ema_12`）
    是為了讓同一種特徵能出現多次，而代價就是這裡：改參數是一個牽動兩個地方的
    操作。用序號當名字（`feature_0`）可以避開它，但那樣設定檔就再也讀不懂了。

    它是 domain service：吃註冊表（具體實例，不是 Protocol）與一個值，回一串值。
    """

    def __init__(self, *, features: FeatureRegistry) -> None:
        self._features = features

    def expand(self, space: SearchSpace) -> tuple[StrategySpecification, ...]:
        expanded: list[StrategySpecification] = []
        for combination in product(*(axis.values for axis in space.axes)):
            specification = self._apply_all(space, combination)
            if specification is not None:
                expanded.append(specification)
        if not expanded:
            raise ValueError("剪枝之後一個組合都不剩，檢查一下限制條件")
        return tuple(expanded)

    def pruned_count(self, space: SearchSpace) -> int:
        """被剪掉幾個組合。報告要印它，否則讀的人以為搜尋涵蓋了全部組合。"""
        return space.unconstrained_combination_count - len(self.expand(space))

    def _apply_all(
        self, space: SearchSpace, combination: tuple[ParameterValue, ...]
    ) -> StrategySpecification | None:
        specification = space.base
        for axis, value in zip(space.axes, combination, strict=True):
            specification = self._apply(specification, axis, value)
        if not self._satisfies(specification, space.constraints):
            return None
        return self._named(specification, space, combination)

    def _apply(
        self,
        specification: StrategySpecification,
        axis: SearchAxis,
        value: ParameterValue,
    ) -> StrategySpecification:
        if isinstance(axis, FeatureParameterAxis):
            return self._with_feature_parameter(specification, axis, value)
        return self._with_condition_parameter(specification, axis, value)

    def _with_feature_parameter(
        self,
        specification: StrategySpecification,
        axis: FeatureParameterAxis,
        value: ParameterValue,
    ) -> StrategySpecification:
        if axis.feature_index >= len(specification.features):
            raise ValueError(
                f"{axis.label} 指到第 {axis.feature_index} 個特徵，"
                f"但這份設定只有 {len(specification.features)} 個"
            )
        original = specification.features[axis.feature_index]
        updated = FeatureSpecification(
            kind=original.kind,
            parameters={**original.parameters, axis.key: value},
        )
        features = list(specification.features)
        features[axis.feature_index] = updated

        previous_name = self._features.build(original).name
        current_name = self._features.build(updated).name
        return replace(
            specification,
            features=tuple(features),
            entry=self._renamed(specification.entry, previous_name, current_name),
            exit=self._renamed(specification.exit, previous_name, current_name),
            filters=(
                None
                if specification.filters is None
                else self._renamed(specification.filters, previous_name, current_name)
            ),
        )

    def _with_condition_parameter(
        self,
        specification: StrategySpecification,
        axis: ConditionParameterAxis,
        value: ParameterValue,
    ) -> StrategySpecification:
        if axis.tree is ConditionTree.ENTRY:
            return replace(
                specification,
                entry=self._rewritten(specification.entry, axis.key, value),
            )
        if axis.tree is ConditionTree.EXIT:
            return replace(
                specification,
                exit=self._rewritten(specification.exit, axis.key, value),
            )
        if specification.filters is None:
            raise ValueError(f"{axis.label} 指向 filters，但這份設定沒有 filters")
        return replace(
            specification,
            filters=self._rewritten(specification.filters, axis.key, value),
        )

    @classmethod
    def _renamed(
        cls, node: ConditionSpecification, previous: str, current: str
    ) -> ConditionSpecification:
        """把條件參數裡等於舊特徵名的值換成新名字，遞迴整棵樹。

        比對的是**值**而不是鍵，因為特徵名出現在 `fast`／`slow`／`feature`／`left`
        這些不同的鍵上，而它們的共同點只有「值是一個特徵名」。
        """
        parameters = {
            key: (current if value == previous else value)
            for key, value in node.parameters.items()
        }
        return ConditionSpecification(
            kind=node.kind,
            parameters=parameters,
            children=tuple(
                cls._renamed(child, previous, current) for child in node.children
            ),
        )

    @classmethod
    def _rewritten(
        cls, node: ConditionSpecification, key: str, value: ParameterValue
    ) -> ConditionSpecification:
        """把整棵樹裡叫這個名字的參數都換成新值。"""
        parameters = dict(node.parameters)
        if key in parameters:
            parameters[key] = value
        return ConditionSpecification(
            kind=node.kind,
            parameters=parameters,
            children=tuple(
                cls._rewritten(child, key, value) for child in node.children
            ),
        )

    @staticmethod
    def _satisfies(
        specification: StrategySpecification,
        constraints: tuple[IncreasingPeriodConstraint, ...],
    ) -> bool:
        for constraint in constraints:
            faster = specification.features[constraint.faster_feature_index]
            slower = specification.features[constraint.slower_feature_index]
            if float(faster.parameters[constraint.key]) >= float(
                slower.parameters[constraint.key]
            ):
                return False
        return True

    @staticmethod
    def _named(
        specification: StrategySpecification,
        space: SearchSpace,
        combination: tuple[ParameterValue, ...],
    ) -> StrategySpecification:
        """名字帶上這一組參數，這樣結果表的每一列都指得回它的設定。

        沒有這個的話，五十列同名的結果沒辦法對回任何東西——而「回測結果對不回
        設定」跟沒有做過那次回測差不多。
        """
        suffix = "_".join(
            f"{axis.key}{value}"
            for axis, value in zip(space.axes, combination, strict=True)
        )
        return replace(specification, name=f"{space.base.name}__{suffix}")
