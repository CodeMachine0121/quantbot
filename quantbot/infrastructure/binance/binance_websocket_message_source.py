# quantbot/infrastructure/binance/binance_websocket_message_source.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import connect

from quantbot.domain.values.listing import Listing
from quantbot.infrastructure.binance.binance_stream_url_builder import (
    BinanceStreamUrlBuilder,
)


class BinanceWebsocketMessageSource:
    """一條會自己重連的 WebSocket 連線，吐出原始的文字訊息。

    重連邏輯只寫在這裡一份。兩個 stream（成交與掛單簿）都走這條路，所以「斷線要
    等多久再試」這件事不會有兩種行為。

    退避是指數的並且有上限：斷線的原因通常不是我們這邊的問題（交易所重啟、網路
    抖動），一秒重試一百次只會讓自己被擋。上限存在的理由相反——真的是長時間中斷
    的話，退避不能無限長大到「服務恢復了兩小時我們還在睡」。

    心跳不必自己處理：websockets 這個套件預設每 20 秒送一次 ping，對方沒回就
    主動關閉連線，而關閉會讓下面的 async for 結束、外層迴圈重連。自己實作 ping
    只會多一份要維護的計時器。
    """

    def __init__(
        self,
        url_builder: BinanceStreamUrlBuilder,
        *,
        initial_backoff_seconds: float = 1.0,
        maximum_backoff_seconds: float = 30.0,
    ) -> None:
        self._url_builder = url_builder
        self._initial_backoff_seconds = initial_backoff_seconds
        self._maximum_backoff_seconds = maximum_backoff_seconds

    async def messages(
        self, listing: Listing, *, streams: tuple[str, ...]
    ) -> AsyncIterator[str]:
        url = self._url_builder.combined_stream(listing, streams=streams)
        backoff_seconds = self._initial_backoff_seconds

        while True:
            try:
                async with connect(url, max_queue=1024) as connection:
                    backoff_seconds = self._initial_backoff_seconds  # 連上了就重設
                    async for frame in connection:
                        yield frame if isinstance(frame, str) else frame.decode("utf-8")
            except OSError, websockets.WebSocketException:
                # 斷線是預期事件，不是例外狀況。往上丟的話呼叫端每隔幾小時就要
                # 處理一次同樣的錯誤，而它能做的也只有重連。
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(
                    backoff_seconds * 2, self._maximum_backoff_seconds
                )
