# quantbot/domain/values/market.py
from enum import StrEnum


class Market(StrEnum):
    """交易的市場。

    現貨與永續合約的資料 NEVER 混用，所以它是列舉而不是字串——拼錯的市場
    名稱在建立 Instrument 的那一刻就會失敗，不會等到組出網址才發現。
    """

    SPOT = "spot"
    USD_MARGINED_PERPETUAL = "usdm"
