# quantbot/domain/interfaces/feature.py
from typing import Protocol

import pandas as pd

from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class Feature(Protocol):
    """一個特徵：吃一份市場原料，回傳一條與 K 線等長、index 相同的序列。

    它跟 Day 04 的 Indicator 是兩件不同的事，所以是兩個型別：

    - Indicator 是 ABC，因為它有共用實作要給子類別（檢查欄位、轉型、貼名字），
      而且它只吃 K 線的一個欄位。
    - Feature 是 Protocol，因為它的實作沒有共用骨架可分——從掛單簿算的、從逐筆
      成交算的、從 K 線算的，中間沒有一行程式碼是一樣的。

    介面在**第一個特徵出現的這一天**就訂死，不等到 Day 15 收斂時才回頭統一。
    Day 04 為三個指標訂 Indicator 時是同樣的判斷：中途改介面的成本是所有實作、
    所有測試、所有呼叫端一起改。

    required_inputs 是這個介面最重要的一條。它讓「這個特徵需要什麼資料」變成
    算之前就問得出來的事，Day 15 的管線因此可以在載入設定時就擋掉跑不起來的組合。
    """

    @property
    def name(self) -> str:
        """輸出序列的名字，慣例是 {feature}_{參數}。"""
        ...

    @property
    def warmup_bar_count(self) -> int:
        """前幾根不能用。整條特徵管線的暖機期是所有特徵裡最長的那一個。"""
        ...

    @property
    def required_inputs(self) -> frozenset[MarketInput]: ...

    def compute(self, view: MarketView) -> pd.Series: ...
