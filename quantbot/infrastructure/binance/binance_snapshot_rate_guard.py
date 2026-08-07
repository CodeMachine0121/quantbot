# quantbot/infrastructure/binance/binance_snapshot_rate_guard.py
from __future__ import annotations

import asyncio

import pandas as pd

from quantbot.domain.interfaces.clock import Clock


class BinanceSnapshotRateGuard:
    """限制重拉快照的頻率。

    Day 03 的 BinanceRateLimitGuard 管的是回補時的 weight 帳，它讀 ccxt 的回應
    標頭、逼近門檻就讓路。這裡要防的是另一種形狀的問題：**序號斷裂風暴**。

    掛單簿的增量更新每 100ms 來一次，序號一斷就要重拉快照。網路品質差的時候，
    「斷裂 → 重拉 → 又斷 → 又重拉」可以在幾秒內打幾十次 /api/v3/depth，
    每次 5 weight（100 檔以內）。撞到每分鐘 2400 weight 的上限之後，IP 會被
    暫時封鎖，而那條路徑同時是回補與（第四階段）下單在用的。

    所以這個 guard 的規則很簡單：兩次快照之間至少隔 minimum_interval_seconds。
    在那之前想重拉的話就等——寧可有幾秒沒有掛單簿資料，也 NEVER 把整個 IP 賠掉。
    """

    def __init__(self, clock: Clock, *, minimum_interval_seconds: float = 2.0) -> None:
        self._clock = clock
        self._minimum_interval_seconds = minimum_interval_seconds
        self._latest_acquired_at: pd.Timestamp | None = None

    async def acquire(self) -> None:
        """要打快照之前呼叫。太密的話睡到可以打為止。"""
        now = self._clock.now()
        if self._latest_acquired_at is not None:
            elapsed_seconds = (now - self._latest_acquired_at).total_seconds()
            remaining_seconds = self._minimum_interval_seconds - elapsed_seconds
            if remaining_seconds > 0:
                await asyncio.sleep(remaining_seconds)
                now = self._clock.now()
        self._latest_acquired_at = now
