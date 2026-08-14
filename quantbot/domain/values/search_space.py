# quantbot/domain/values/search_space.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quantbot.domain.values.feature_parameters import ParameterValue
from quantbot.domain.values.strategy_specification import StrategySpecification


class ConditionTree(StrEnum):
    """一份策略設定裡的三棵樹。搜尋軸要指定改哪一棵。"""

    ENTRY = "entry"
    EXIT = "exit"
    FILTERS = "filters"


@dataclass(frozen=True)
class FeatureParameterAxis:
    """把某一個特徵的某個參數換成幾個值。

    它有一個不明顯但重要的副作用：**改了參數就改了特徵的名字。** `ema` 的 period
    從 12 變成 8，特徵名就從 `ema_12` 變成 `ema_8`，而條件樹裡引用舊名字的地方
    全部會對不上。所以展開的時候必須連帶改寫條件引用的名字，而那件事需要註冊表
    才算得出新名字——這就是展開為什麼是一個 domain service 而不是這個值的方法。
    """

    feature_index: int
    key: str
    values: tuple[ParameterValue, ...]

    def __post_init__(self) -> None:
        if self.feature_index < 0:
            raise ValueError(f"feature_index 不能是負數，收到 {self.feature_index}")
        if not self.values:
            raise ValueError(f"{self.key} 這個軸至少要有一個值")

    @property
    def label(self) -> str:
        return f"features[{self.feature_index}].{self.key}"


@dataclass(frozen=True)
class ConditionParameterAxis:
    """把某一棵條件樹裡叫某個名字的參數換成幾個值。

    它改的是「這棵樹裡所有叫這個名字的參數」，而不是某一個節點。理由是路徑
    （第幾層的第幾個子節點）在設定檔裡沒有名字，寫進搜尋空間會變成一串看不懂的
    數字；而實務上一棵樹裡同名的參數幾乎都是同一件事（`value` 就是那個閾值）。

    代價是表達力有上限：一棵有兩個不同閾值的樹沒辦法只調其中一個。那種情況要
    另外寫一份設定檔，而這個限制是刻意的——搜尋空間越容易長大，本篇的結論就越
    適用（見 Day 21）。
    """

    tree: ConditionTree
    key: str
    values: tuple[ParameterValue, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError(f"{self.key} 這個軸至少要有一個值")

    @property
    def label(self) -> str:
        return f"{self.tree}.{self.key}"


SearchAxis = FeatureParameterAxis | ConditionParameterAxis


@dataclass(frozen=True)
class IncreasingPeriodConstraint:
    """兩個特徵的某個參數必須嚴格遞增。

    它存在的理由是領域知識而不是效能：「快線的週期比慢線長」的組合不是一個
    比較差的策略，它是一個**講不通**的策略——快線慢線交叉的意義來自兩者的
    反應速度差，反過來就沒有那個意義了。

    剪枝要用這種說得出理由的規則，NEVER 用「跑起來太慢」當理由。後者會剪掉
    講得通的組合，而那等於偷偷縮小搜尋空間又不記錄。
    """

    faster_feature_index: int
    slower_feature_index: int
    key: str = "period"


@dataclass(frozen=True)
class SearchSpace:
    """一份基準設定 ＋ 幾個要掃的軸 ＋ 幾條剪枝規則。

    組合數是各軸長度的乘積，而它長得非常快：三個軸各 4 個值就是 64 種，
    加一個軸變 256 種。這件事在 Day 21 是主題而不是註腳。
    """

    base: StrategySpecification
    axes: tuple[SearchAxis, ...]
    constraints: tuple[IncreasingPeriodConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError("搜尋空間至少要有一個軸")

    @property
    def unconstrained_combination_count(self) -> int:
        """還沒剪枝的組合數。它跟剪枝後的差距是搜尋空間報告要印出來的東西。"""
        total = 1
        for axis in self.axes:
            total *= len(axis.values)
        return total
