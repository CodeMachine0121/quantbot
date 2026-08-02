# quantbot/domain/interfaces/reference_price_source.py
from typing import Protocol

import pandas as pd

from quantbot.domain.values.time_range import TimeRange


class ReferencePriceSource(Protocol):
    """對照組：一個獨立於主來源的價格來源。

    Day 01 的第五條選型原則（每個主來源都要有對照組）在程式碼裡就是這個介面。
    """

    @property
    def name(self) -> str:
        """報告裡要標出對照組是誰，所以名字是介面的一部分。"""
        ...

    def supports(self, symbol: str) -> bool:
        """沒有對照來源的交易對要在報告裡標成 SKIP，NEVER 默默當成通過。"""
        ...

    async def daily_close(self, symbol: str, period: TimeRange) -> pd.Series: ...
