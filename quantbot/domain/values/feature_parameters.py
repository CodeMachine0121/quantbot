# quantbot/domain/values/feature_parameters.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar

ParameterValue = int | float | str


@dataclass(frozen=True)
class FeatureParameters:
    """從設定檔讀進來的一組特徵參數，帶型別檢查與未使用檢查。

    設定檔的值是弱型別的：YAML 的 `period: 14` 是 int，`period: "14"` 是 str，
    而 `perid: 14`（拼錯）是一個完全合法的 YAML。三種都不該讓程式跑到一半才炸。

    所以取值一律走 integer()／number()／text()，它們負責轉型與報錯；而 ensure_used()
    負責抓拼錯的欄名——**那是這個類別存在最重要的理由**。少了它，一個拼錯的參數
    會被安靜忽略，於是使用者以為自己在跑 period=50，實際上跑的是預設值 14。
    """

    EMPTY: ClassVar[Mapping[str, ParameterValue]] = MappingProxyType({})

    values: Mapping[str, ParameterValue] = EMPTY
    _consumed: set[str] = field(default_factory=set, compare=False, repr=False)

    def integer(self, name: str, default: int | None = None) -> int:
        raw = self._take(name, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError(f"{name} 應該是整數，實得 {raw!r}")
        converted = int(raw)
        if float(raw) != converted:
            raise ValueError(f"{name} 應該是整數，實得 {raw!r}")
        return converted

    def number(self, name: str, default: float | None = None) -> float:
        raw = self._take(name, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError(f"{name} 應該是數字，實得 {raw!r}")
        return float(raw)

    def text(self, name: str, default: str | None = None) -> str:
        raw = self._take(name, default)
        return str(raw)

    def ensure_used(self) -> None:
        """所有給進來的參數都被取用過了嗎。

        沒被取用的參數幾乎一定是拼錯的欄名，所以這裡丟例外而不是警告。
        Day 17 的設定檔載入器會在載入時呼叫它，讓錯誤在啟動時就出現，
        NEVER 等到跑完一輪回測才發現參數沒生效。
        """
        unused = set(self.values) - self._consumed
        if unused:
            raise ValueError(f"沒有被使用的參數：{sorted(unused)}")

    def _take(self, name: str, default: ParameterValue | None) -> ParameterValue:
        self._consumed.add(name)
        if name in self.values:
            return self.values[name]
        if default is None:
            raise ValueError(f"缺少必要參數 {name}")
        return default
