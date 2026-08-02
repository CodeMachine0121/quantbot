# quantbot/infrastructure/binance/binance_rate_limit_guard.py
from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

import pandas as pd


class BinanceRateLimitGuard:
    """限流的兩種等待。

    yield_if_heavy 是預防性的：讀回應標頭，逼近門檻就主動睡到下一分鐘。
    call 是被動的：撞到暫時性錯誤才退避重試。只有後者的程式會一直在上限
    邊緣震盪，兩個都要有。

    門檻與退避參數是 Binance 的細節，所以這個類別住在 infrastructure。
    """

    WEIGHT_HEADER: ClassVar[str] = "x-mbx-used-weight-1m"
    # 每分鐘上限 2400 的一半，另一半留給帳戶查詢與下單
    DEFAULT_WEIGHT_CEILING: ClassVar[int] = 1200

    def __init__(
        self,
        *,
        weight_ceiling: int = DEFAULT_WEIGHT_CEILING,
        attempt_limit: int = 5,
        base_delay_seconds: float = 1.0,
    ) -> None:
        self._weight_ceiling = weight_ceiling
        self._attempt_limit = attempt_limit
        self._base_delay_seconds = base_delay_seconds

    async def call(self, operation: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        """指數退避重試。只重試暫時性錯誤，參數錯誤之類的直接往上丟。"""
        import ccxt.async_support as ccxt

        transient = (
            ccxt.RateLimitExceeded,
            ccxt.NetworkError,
            ccxt.ExchangeNotAvailable,
        )
        for attempt in range(self._attempt_limit):
            try:
                return await operation()
            except transient:
                if attempt == self._attempt_limit - 1:
                    raise
                # 加上抖動，避免多個併發任務同時醒來再撞一次
                delay = self._base_delay_seconds * 2**attempt + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

    async def yield_if_heavy(self, exchange: Any) -> None:
        """讀 X-MBX-USED-WEIGHT-1M，逼近門檻就主動睡到下一分鐘。"""
        used_weight = self._read_header(exchange, self.WEIGHT_HEADER)
        if used_weight is not None and int(used_weight) > self._weight_ceiling:
            await asyncio.sleep(60 - pd.Timestamp.now(tz="UTC").second)

    @staticmethod
    def _read_header(exchange: Any, name: str) -> str | None:
        """標頭大小寫不保證，統一轉小寫比對。"""
        headers = {
            key.lower(): value
            for key, value in (exchange.last_response_headers or {}).items()
        }
        return headers.get(name)
