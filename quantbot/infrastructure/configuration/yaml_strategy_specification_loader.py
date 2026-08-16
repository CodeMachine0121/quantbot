# quantbot/infrastructure/configuration/yaml_strategy_specification_loader.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from quantbot.domain.values.condition_specification import ConditionSpecification
from quantbot.domain.values.feature_specification import FeatureSpecification
from quantbot.domain.values.holding_rules import HoldingRules
from quantbot.domain.values.position_direction import PositionDirection
from quantbot.domain.values.strategy_specification import StrategySpecification

COMPOSITE_KINDS = frozenset({"all", "any", "not", "sustained"})


class YamlStrategySpecificationLoader:
    """讀一份策略 YAML，變成一個 StrategySpecification。

    格式沿用 Day 15 的兩個決定：參數跟 kind 平放在同一層、而 kind 是保留字。條件多了
    一個保留字 `of`，用來放子節點：

        name: trend_ema_rsi
        features:
          - kind: ema
            period: 12
        entry:
          kind: crossover
          fast: ema_12
          direction: up
          slow: ema_26
        filters:
          kind: not
          of:
            - kind: threshold
              feature: rsi_14
              comparison: above
              value: 70

    這個類別只負責「YAML 長得對不對」——該有的鍵在不在、該是清單的地方是不是清單、
    值是不是純量。**參數的值一律不驗證**，那是 builder 的事。分開的好處是錯誤訊息
    不會混在一起：格式錯誤說「entry 少了 kind」，參數錯誤說「comparison 只能是
    ['above', 'below', 'at_least', 'at_most']」。

    組合節點的 kind 有一份白名單。理由是「哪些 kind 可以有子節點」是格式層面的
    問題（`of` 出現在不該出現的地方要當成格式錯誤），而註冊表那邊還會再擋一次
    語意層面的問題（`not` 只能有一個子節點）。兩道檢查的訊息不同，而且都指得出
    是設定檔的哪個位置。
    """

    def load(self, path: Path) -> StrategySpecification:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError(f"{path} 的最外層應該是一個對映")

        name = document.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{path} 缺少 name")
        for required in ("features", "entry", "exit"):
            if required not in document:
                raise ValueError(f"{path} 缺少 {required}")

        filters = document.get("filters")
        return StrategySpecification(
            name=name,
            features=self._features(document["features"], path),
            entry=self._condition(document["entry"], "entry"),
            exit=self._condition(document["exit"], "exit"),
            filters=None if filters is None else self._condition(filters, "filters"),
            holding=self._holding(document.get("holding")),
            direction=PositionDirection.parse(
                str(document.get("direction", PositionDirection.LONG.value))
            ),
        )

    def _features(self, raw: object, path: Path) -> tuple[FeatureSpecification, ...]:
        if not isinstance(raw, Sequence) or isinstance(raw, str):
            raise ValueError(f"{path} 的 features 應該是一個清單")
        return tuple(
            FeatureSpecification(
                kind=str(entry["kind"]),
                parameters=self._scalars(entry, f"features 第 {index} 項", skip="kind"),
            )
            for index, entry in enumerate(self._mappings(raw, "features"), start=1)
        )

    def _condition(self, raw: object, position: str) -> ConditionSpecification:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{position} 應該是一個對映，實得 {raw!r}")
        if "kind" not in raw:
            raise ValueError(f"{position} 少了 kind")

        kind = str(raw["kind"])
        children = raw.get("of")
        if children is not None and kind not in COMPOSITE_KINDS:
            raise ValueError(
                f"{position} 的 {kind} 不能有 of（可以有子節點的只有"
                f" {sorted(COMPOSITE_KINDS)}）"
            )
        if children is None:
            built: tuple[ConditionSpecification, ...] = ()
        else:
            if not isinstance(children, Sequence) or isinstance(children, str):
                raise ValueError(f"{position}.of 應該是一個清單")
            built = tuple(
                self._condition(child, f"{position}.of[{index}]")
                for index, child in enumerate(children)
            )

        return ConditionSpecification(
            kind=kind,
            parameters=self._scalars(raw, position, skip="kind", also_skip="of"),
            children=built,
        )

    def _holding(self, raw: object) -> HoldingRules:
        """holding 是可選的，而且兩個欄位各自可選。"""
        if raw is None:
            return HoldingRules.unbounded()
        if not isinstance(raw, Mapping):
            raise ValueError(f"holding 應該是一個對映，實得 {raw!r}")
        unknown = sorted(set(map(str, raw)) - {"maximum_holding_bars", "cooldown_bars"})
        if unknown:
            raise ValueError(f"holding 有不認識的欄位：{unknown}")
        return HoldingRules(
            maximum_holding_bars=self._optional_integer(raw, "maximum_holding_bars"),
            cooldown_bars=self._optional_integer(raw, "cooldown_bars"),
        )

    @staticmethod
    def _optional_integer(raw: Mapping[object, object], key: str) -> int | None:
        if key not in raw:
            return None
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"holding.{key} 應該是整數，實得 {value!r}")
        return value

    @staticmethod
    def _mappings(
        raw: Sequence[object], position: str
    ) -> list[Mapping[object, object]]:
        mappings: list[Mapping[object, object]] = []
        for index, entry in enumerate(raw, start=1):
            if not isinstance(entry, Mapping):
                raise ValueError(f"{position} 第 {index} 項應該是一個對映")
            if "kind" not in entry:
                raise ValueError(f"{position} 第 {index} 項少了 kind")
            mappings.append(entry)
        return mappings

    @staticmethod
    def _scalars(
        raw: Mapping[object, object],
        position: str,
        *,
        skip: str,
        also_skip: str | None = None,
    ) -> dict[str, int | float | str]:
        """把保留字之外的鍵收成參數，並擋掉非純量的值。

        擋非純量是為了讓錯誤訊息停在正確的地方：一個把 `value: [70]` 寫成清單的
        設定檔，如果放行到 builder，看到的會是「value 應該是數字，實得 [70]」——
        訊息沒錯，但它指不出是設定檔的哪一行。
        """
        skipped = {skip} if also_skip is None else {skip, also_skip}
        parameters: dict[str, int | float | str] = {}
        for key, value in raw.items():
            name = str(key)
            if name in skipped:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError(
                    f"{position} 的 {name} 只能是數字或字串，實得 {value!r}"
                )
            parameters[name] = value
        return parameters
