# quantbot/infrastructure/binance/binance_stream_payload_parser.py
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import ClassVar

import pandas as pd

from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.price_level import PriceLevel
from quantbot.domain.values.trade_columns import TradeColumns
from quantbot.domain.values.trade_event import TradeEvent


class BinanceStreamPayloadParser:
    """把 Binance 的 JSON 轉成 domain 的值。所有欄名縮寫的知識都關在這裡。

    Binance 的即時訊息用單字母欄名（a、p、q、U、u、b、m），這在頻寬上是對的，
    在可讀性上是災難。這個類別是唯一知道那些字母代表什麼的地方。

    每個欄位都經過一次型別檢查再落地。這看起來囉唆，但外部 JSON 是型別系統的
    邊界：這裡不擋，`price` 就會是一個「可能是字串、可能是數字、可能不存在」的
    東西，一路飄進計算才炸，而且炸出來的訊息跟真正的原因無關。
    """

    # 兩個 stream 的名字。@100ms 是掛單簿增量的推送頻率，不寫的話預設 1000ms。
    AGG_TRADE_STREAM: ClassVar[str] = "aggTrade"
    DEPTH_STREAM: ClassVar[str] = "depth@100ms"

    def stream_name(self, frame: str) -> str:
        """合併訂閱時，外層會多包一層 {"stream": ..., "data": ...}。"""
        return self._text(self._decode(frame), "stream")

    def agg_trade(self, frame: str) -> TradeEvent:
        payload = self._payload(frame)
        return TradeEvent(
            transact_time=self._moment(self._integer(payload, "T")),
            trade_id=self._integer(payload, "a"),
            first_trade_id=self._integer(payload, "f"),
            last_trade_id=self._integer(payload, "l"),
            price=self._number(payload, "p"),
            quantity=self._number(payload, "q"),
            buyer_is_maker=self._flag(payload, "m"),
        )

    def depth_update(self, frame: str) -> OrderBookUpdate:
        payload = self._payload(frame)
        return OrderBookUpdate(
            event_time=self._moment(self._integer(payload, "E")),
            first_update_id=self._integer(payload, "U"),
            final_update_id=self._integer(payload, "u"),
            bid_changes=self._levels(payload, "b"),
            ask_changes=self._levels(payload, "a"),
        )

    def snapshot(self, payload_bytes: bytes) -> OrderBookSnapshot:
        """REST 的深度快照。欄名在這條路徑上是完整單字，跟 WebSocket 不一樣。"""
        payload = self._decode(payload_bytes.decode("utf-8"))
        return OrderBookSnapshot(
            last_update_id=self._integer(payload, "lastUpdateId"),
            bids=self._levels(payload, "bids"),
            asks=self._levels(payload, "asks"),
        )

    def _payload(self, frame: str) -> Mapping[str, object]:
        """剝掉合併訂閱的外層信封。單一 stream 沒有信封，所以兩種都要收。"""
        decoded = self._decode(frame)
        inner = decoded.get("data")
        if inner is None:
            return decoded
        if not isinstance(inner, Mapping):
            raise ValueError(f"data 不是物件：{inner!r}")
        return {str(key): value for key, value in inner.items()}

    @staticmethod
    def _decode(frame: str) -> Mapping[str, object]:
        decoded = json.loads(frame)
        if not isinstance(decoded, Mapping):
            raise ValueError(f"訊息不是 JSON 物件：{frame[:120]!r}")
        return {str(key): value for key, value in decoded.items()}

    @staticmethod
    def _moment(epoch: int) -> pd.Timestamp:
        """單位判斷借 TradeColumns 那一份，不在這裡再寫一張對照表。

        即時串流目前給的是毫秒、批次檔給的是微秒，而兩邊的資料會進同一張表。
        單位判斷只要有兩份，總有一天會有一份沒跟著改。
        """
        return pd.Timestamp(TradeColumns.to_utc(pd.Series([epoch])).iloc[0])

    @staticmethod
    def _text(payload: Mapping[str, object], key: str) -> str:
        value = payload[key]
        if not isinstance(value, str):
            raise ValueError(f"{key} 應該是字串，實得 {value!r}")
        return value

    @staticmethod
    def _integer(payload: Mapping[str, object], key: str) -> int:
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} 應該是整數，實得 {value!r}")
        return value

    @staticmethod
    def _number(payload: Mapping[str, object], key: str) -> float:
        """價格與數量在 Binance 的 JSON 裡是**字串**，不是數字。

        這是刻意的：字串不會在傳輸過程中被某一端的 JSON 實作重新格式化成
        科學記號或截掉尾數。代價是每個數值欄位都要自己轉，忘了轉的話
        pandas 會安靜地給我們一整欄 object 型別的字串。
        """
        value = payload[key]
        if isinstance(value, str):
            return float(value)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} 應該是數字或數字字串，實得 {value!r}")
        return float(value)

    @staticmethod
    def _flag(payload: Mapping[str, object], key: str) -> bool:
        value = payload[key]
        if not isinstance(value, bool):
            raise ValueError(f"{key} 應該是布林，實得 {value!r}")
        return value

    @classmethod
    def _levels(cls, payload: Mapping[str, object], key: str) -> tuple[PriceLevel, ...]:
        """每一檔是 ["價格", "數量"] 這樣的兩元素陣列，兩個都是字串。"""
        raw = payload[key]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError(f"{key} 應該是陣列，實得 {raw!r}")

        levels: list[PriceLevel] = []
        for entry in raw:
            if (
                not isinstance(entry, Sequence)
                or isinstance(entry, (str, bytes))
                or len(entry) < 2
            ):
                raise ValueError(f"{key} 的一檔格式不對：{entry!r}")
            levels.append(
                PriceLevel(price=float(str(entry[0])), quantity=float(str(entry[1])))
            )
        return tuple(levels)
