# quantbot/domain/interfaces/trade_parser.py
from typing import Protocol

import pandas as pd


class TradeParser(Protocol):
    """把外部格式的位元組轉成一張逐筆成交的表。

    「第幾欄是什麼」是交易所的格式知識，所以它住在 infrastructure；domain 只
    宣告「有人負責把位元組變成對齊過的表」。
    """

    def parse(self, payload: bytes) -> pd.DataFrame: ...
