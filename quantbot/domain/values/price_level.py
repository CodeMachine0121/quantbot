# quantbot/domain/values/price_level.py
from dataclasses import dataclass


@dataclass(frozen=True)
class PriceLevel:
    """掛單簿上的一檔：這個價格上總共掛了多少量。

    quantity 為 0 有特殊語意——在增量更新裡它代表「這一檔被清空了」，
    要從簿子上移除，而不是留一個掛 0 的價位。
    """

    price: float
    quantity: float

    @property
    def is_removal(self) -> bool:
        return self.quantity == 0.0
