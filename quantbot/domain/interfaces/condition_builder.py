# quantbot/domain/interfaces/condition_builder.py
from typing import Protocol

from quantbot.domain.strategies.condition import Condition
from quantbot.domain.values.feature_parameters import FeatureParameters


class ConditionBuilder(Protocol):
    """把一組設定檔參數與（可能的）子節點變成一個條件物件。

    跟 Day 15 的 FeatureBuilder 是同一個設計，理由也一樣：註冊表若直接放類別再
    `cls(**parameters)` 就是反射式分派，型別檢查器看不到裡面發生什麼事，參數名一改
    就在執行期才炸。builder 讓「crossover 需要 fast、direction、slow 三個參數，
    而 direction 只能是 up 或 down」變成 mypy 檢查得到的普通程式碼。

    多出來的 children 參數是條件比特徵複雜的地方：組合節點的參數是它的子節點，
    而子節點在進到 builder 之前已經被註冊表遞迴建好了。所以 builder 永遠只處理
    「這一層」，不必自己遞迴。
    """

    @property
    def kind(self) -> str:
        """設定檔裡用的字串。它是這個 builder 在註冊表裡的鍵。"""
        ...

    def build(
        self, parameters: FeatureParameters, children: tuple[Condition, ...]
    ) -> Condition: ...
