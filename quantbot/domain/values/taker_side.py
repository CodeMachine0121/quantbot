# quantbot/domain/values/taker_side.py
from __future__ import annotations

from enum import StrEnum


class TakerSide(StrEnum):
    """這筆成交是被誰吃掉的：主動買進，還是主動賣出。

    每一筆成交都同時有買方與賣方，所以「這筆是買還是賣」本身不是問題——
    有意義的問題是**誰是主動的那一方**。掛在簿子上等的是 maker，
    衝過來成交的是 taker，而 taker 的方向才是資金流的方向。

    官方資料給的是 is_buyer_maker：買方掛單的話，主動的是賣方。
    這個轉換只寫在 from_buyer_is_maker() 一份，NEVER 在呼叫端手動反轉——
    寫反了不會報錯，只會讓後面每個資金流特徵的正負號整批顛倒。
    """

    BUY = "buy"
    SELL = "sell"

    @classmethod
    def from_buyer_is_maker(cls, buyer_is_maker: bool) -> TakerSide:
        return cls.SELL if buyer_is_maker else cls.BUY
