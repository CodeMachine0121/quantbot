# quantbot/domain/strategies/condition.py
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Condition(ABC):
    """一個條件：吃一張特徵表，回一條與它同 index 的布林序列。

    這是第三階段的基本單位。契約只有一條線那麼窄——一張表進去、一條布林序列
    出來——而那個窄契約正是條件能互相組合的前提：兩個回傳同一種形狀的東西，
    才有辦法用 and / or / not 接起來，接完的結果又還是同一種形狀。

    它用 ABC 而不是 Protocol，理由跟 Day 04 的 Indicator 一樣：這個家族有共用
    實作要給子類別。而且這裡的共用實作比 Indicator 更多——除了 evaluate() 擔保的
    三件事（欄位檢查、布林化、貼名字）之外，三個運算子與 describe() 也是所有
    子類別共用的。對外相依才用 Protocol，那是 Day 10 的 Feature。

    子類別只需要實作四件事：name、required_features、warmup_bar_count、_evaluate。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """輸出序列的名字。它也是報告與日誌裡指認這個節點的方式。"""

    @property
    @abstractmethod
    def required_features(self) -> frozenset[str]:
        """這個條件要讀特徵表的哪幾欄。

        它是整個第三階段最重要的一個屬性。使用者在設定檔裡寫的是條件，而條件
        需要哪些特徵是**推導得出來的**，NEVER 要使用者自己再宣告一次——宣告兩次
        就會有兩份真相，而漏掉一個的下場是整欄 NaN 配上一個永遠不成立的條件。
        """

    @property
    @abstractmethod
    def warmup_bar_count(self) -> int:
        """這個條件本身要幾根才答得出話。

        它跟特徵的暖機期是兩件事：特徵的暖機期由 Day 15 的管線切掉，這裡算的是
        **條件在那之上還要多少根**。交叉要看前一根的狀態，所以是 1；閾值不用，
        所以是 0。
        """

    @abstractmethod
    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        """真正的判斷。回傳布林序列，缺值一律當成「不成立」。

        缺值當 False 是刻意的，而且要在每個子類別自己的算式裡就成立：NaN 的意思是
        「這裡答不出來」，而答不出來時不進場永遠比猜一個方向安全。pandas 的比較
        運算對 NaN 一律回 False，所以多數子類別不必為此多寫一行。
        """

    def evaluate(self, table: pd.DataFrame) -> pd.Series:
        """對外的入口。契約的三件事在這裡一次擔保。

        欄位檢查放在這裡而不是各子類別，是因為錯誤訊息要一致：缺欄位時要說清楚
        缺哪一欄、有哪些可用，否則使用者拼錯一個特徵名之後看到的會是 KeyError
        加一個裸欄名，得自己回頭去對設定檔。
        """
        available = frozenset(str(column) for column in table.columns)
        missing = sorted(self.required_features - available)
        if missing:
            raise KeyError(
                f"{self.name} 需要的欄位不在表裡：{missing}"
                f"（表裡有：{sorted(available)}）"
            )
        return self._evaluate(table).astype(bool).rename(self.name)

    def describe(self) -> str:
        """條件樹的可讀形式。組合條件會遞迴展開，所以整棵樹印得出來。

        它不只是給人看的：Day 28 的交易日誌要記下「哪幾個節點成立」，而那份
        紀錄必須認得出節點。名字就是識別，所以它從今天開始就要穩定。
        """
        return self.name

    def __and__(self, other: Condition) -> Condition:
        """兩個都成立。組合的結果還是一個 Condition，所以可以繼續組合。"""
        return AllOf(self, other)

    def __or__(self, other: Condition) -> Condition:
        return AnyOf(self, other)

    def __invert__(self) -> Condition:
        return Not(self)


class AllOf(Condition):
    """全部成立才成立。`a & b & c` 會攤平成一個三元的 AllOf。

    攤平是刻意的：`(a & b) & c` 與 `a & (b & c)` 在邏輯上一樣，但如果照括號建成
    巢狀的樹，兩者的 describe() 與日誌就會長得不一樣，而使用者無法解釋為什麼。
    """

    def __init__(self, *conditions: Condition) -> None:
        if not conditions:
            raise ValueError("AllOf 至少要有一個條件")
        self._conditions = tuple(self._flattened(conditions))

    @staticmethod
    def _flattened(conditions: tuple[Condition, ...]) -> list[Condition]:
        flattened: list[Condition] = []
        for condition in conditions:
            if isinstance(condition, AllOf):
                flattened.extend(condition.conditions)
            else:
                flattened.append(condition)
        return flattened

    @property
    def conditions(self) -> tuple[Condition, ...]:
        return self._conditions

    @property
    def name(self) -> str:
        return "all(" + ", ".join(item.name for item in self._conditions) + ")"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset[str]().union(
            *(item.required_features for item in self._conditions)
        )

    @property
    def warmup_bar_count(self) -> int:
        return max(item.warmup_bar_count for item in self._conditions)

    def describe(self) -> str:
        return "(" + " AND ".join(item.describe() for item in self._conditions) + ")"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        combined = self._conditions[0].evaluate(table)
        for condition in self._conditions[1:]:
            combined = combined & condition.evaluate(table)
        return combined


class AnyOf(Condition):
    """任一成立就成立。"""

    def __init__(self, *conditions: Condition) -> None:
        if not conditions:
            raise ValueError("AnyOf 至少要有一個條件")
        self._conditions = tuple(self._flattened(conditions))

    @staticmethod
    def _flattened(conditions: tuple[Condition, ...]) -> list[Condition]:
        flattened: list[Condition] = []
        for condition in conditions:
            if isinstance(condition, AnyOf):
                flattened.extend(condition.conditions)
            else:
                flattened.append(condition)
        return flattened

    @property
    def conditions(self) -> tuple[Condition, ...]:
        return self._conditions

    @property
    def name(self) -> str:
        return "any(" + ", ".join(item.name for item in self._conditions) + ")"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset[str]().union(
            *(item.required_features for item in self._conditions)
        )

    @property
    def warmup_bar_count(self) -> int:
        return max(item.warmup_bar_count for item in self._conditions)

    def describe(self) -> str:
        return "(" + " OR ".join(item.describe() for item in self._conditions) + ")"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        combined = self._conditions[0].evaluate(table)
        for condition in self._conditions[1:]:
            combined = combined | condition.evaluate(table)
        return combined


class Not(Condition):
    """反過來。

    這裡有一個安靜的陷阱值得記住：`~` 之後，**原本因為缺值而不成立的地方會變成
    成立**。暖機期的 NaN 讓 `rsi_14 > 70` 回 False，取反就變 True，於是一個
    「RSI 沒有超買」的過濾條件在資料還不夠時全部放行。

    所以取反的條件不能單獨當進場依據，要跟一個「資料到位了」的條件 AND 起來。
    這件事引擎會幫上一半——它會把暖機期的那幾根一律壓成不持有，見 StrategyEngine。
    """

    def __init__(self, condition: Condition) -> None:
        self._condition = condition

    @property
    def condition(self) -> Condition:
        return self._condition

    @property
    def name(self) -> str:
        return f"not({self._condition.name})"

    @property
    def required_features(self) -> frozenset[str]:
        return self._condition.required_features

    @property
    def warmup_bar_count(self) -> int:
        return self._condition.warmup_bar_count

    def describe(self) -> str:
        return f"NOT {self._condition.describe()}"

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return ~self._condition.evaluate(table)
