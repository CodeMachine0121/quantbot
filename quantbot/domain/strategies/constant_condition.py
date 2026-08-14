# quantbot/domain/strategies/constant_condition.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.strategies.condition import Condition


class Always(Condition):
    """恆真。

    它有兩個實際用途，都不是「示範」：一是過濾條件的預設值（沒有過濾條件時，
    引擎不必為此寫一個 None 分支），二是 BuyAndHold 的進場條件——那個基準策略
    因此不必是引擎的特例，它就是一個進場恆真、出場恆假的普通策略。

    第二點是這套抽象的一個檢驗。如果連「什麼都不做，抱著就好」都得在引擎裡開一個
    特例，就表示條件這一層切得太窄了。
    """

    @property
    def name(self) -> str:
        return "always"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset()

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return pd.Series(True, index=table.index)


class Never(Condition):
    """恆假。BuyAndHold 的出場條件——它永遠不出場。"""

    @property
    def name(self) -> str:
        return "never"

    @property
    def required_features(self) -> frozenset[str]:
        return frozenset()

    @property
    def warmup_bar_count(self) -> int:
        return 0

    def _evaluate(self, table: pd.DataFrame) -> pd.Series:
        return pd.Series(False, index=table.index)
