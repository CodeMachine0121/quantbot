# quantbot/domain/interfaces/feature_builder.py
from typing import Protocol

from quantbot.domain.interfaces.feature import Feature
from quantbot.domain.values.feature_parameters import FeatureParameters


class FeatureBuilder(Protocol):
    """把一組設定檔參數變成一個特徵物件。

    為什麼需要這一層，而不是讓註冊表直接放類別然後 `cls(**parameters)`：那個寫法
    是反射式分派，型別檢查器完全看不到裡面發生什麼事，而且參數名稱一改就在執行期
    才炸。這個系列禁用反射式分派，理由就是它把錯誤從編譯期推到執行期。

    有了 builder，「obi 這個字串需要 depth_level 與 aggregation 兩個參數、
    後者只能是 mean 或 last」這件事變成一段有型別的普通程式碼，mypy 檢查得到，
    而且參數不合法時的錯誤訊息可以說清楚合法值是什麼。
    """

    @property
    def kind(self) -> str:
        """設定檔裡用的字串。它是這個 builder 在註冊表裡的鍵。"""
        ...

    def build(self, parameters: FeatureParameters) -> Feature: ...
