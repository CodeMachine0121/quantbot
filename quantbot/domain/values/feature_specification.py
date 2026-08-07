# quantbot/domain/values/feature_specification.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from quantbot.domain.values.feature_parameters import FeatureParameters, ParameterValue


@dataclass(frozen=True)
class FeatureSpecification:
    """設定檔裡的一行：要哪一種特徵、用什麼參數。

    它是「使用者寫的東西」與「程式建出來的物件」之間的那一層。有了它，設定檔就
    只需要字串與數字，NEVER 需要 import 任何 Python 類別——這是 Day 16 的策略積木
    庫能用 YAML 表達的前提。

    刻意不在這裡驗證參數。這個值只負責忠實記下使用者說了什麼；驗證要等到知道
    「這個 kind 需要哪些參數」的時候，而那個知識在各自的 builder 手上。
    """

    kind: str
    parameters: Mapping[str, ParameterValue] = FeatureParameters.EMPTY

    def to_parameters(self) -> FeatureParameters:
        return FeatureParameters(values=self.parameters)

    def describe(self) -> str:
        """給錯誤訊息與報告用的一行描述。"""
        if not self.parameters:
            return self.kind
        joined = ", ".join(
            f"{key}={value}" for key, value in sorted(self.parameters.items())
        )
        return f"{self.kind}({joined})"
