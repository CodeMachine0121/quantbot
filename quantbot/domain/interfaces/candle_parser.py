# quantbot/domain/interfaces/candle_parser.py
from typing import Protocol

import pandas as pd


class CandleParser(Protocol):
    """把某種外部格式的位元組解成 K 線的表。

    「第幾欄是什麼」「有沒有標頭」「時間戳是什麼單位」這些知識屬於實作，
    domain 只要求它交回一張欄位對得上 CandleColumns 的表。
    """

    def parse(self, payload: bytes) -> pd.DataFrame: ...
