# quantbot/domain/values/market_input.py
from enum import StrEnum


class MarketInput(StrEnum):
    """一個特徵需要哪幾種原料。

    到 Day 09 為止手上有三種形狀完全不同的資料：規則索引的 K 線、事件流的逐筆成交、
    不規則索引的掛單簿深度摘要。特徵各吃其中一種或幾種。

    把「需要什麼」做成可以被問出來的資料，而不是「算下去缺了就炸」，是為了讓
    Day 15 的管線能在算之前就回答「這組設定跑不跑得起來」。缺原料是設定問題，
    要在載入設定時就報錯，NEVER 等跑到一半才發現。
    """

    CANDLES = "candles"
    TRADES = "trades"
    DEPTH = "depth"
