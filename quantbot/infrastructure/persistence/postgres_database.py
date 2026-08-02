# quantbot/infrastructure/persistence/postgres_database.py
from __future__ import annotations

import asyncpg

from quantbot.config import settings


class PostgresDatabase:
    """asyncpg 連線池的持有者。第一次用到才建立，之後重用。

    做成物件而不是模組層的全域 _pool，是為了測試：要指向另一個資料庫只要建
    另一個 PostgresDatabase，不必 monkeypatch 模組變數，也不會有「上一個測試
    留下的連線池」這種殘留狀態。
    """

    def __init__(
        self,
        dsn: str,
        *,
        minimum_size: int = 1,
        maximum_size: int = 8,
        command_timeout_seconds: int = 60,
    ) -> None:
        self._dsn = dsn
        self._minimum_size = minimum_size
        self._maximum_size = maximum_size
        self._command_timeout_seconds = command_timeout_seconds
        self._pool: asyncpg.Pool | None = None

    @classmethod
    def from_settings(cls) -> PostgresDatabase:
        return cls(settings.postgres_dsn)

    async def pool(self) -> asyncpg.Pool:
        """server_settings 把連線的 timezone 釘死在 UTC，
        避免作業系統的 locale 影響 timestamptz 的輸出。"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=self._minimum_size,
                max_size=self._maximum_size,
                command_timeout=self._command_timeout_seconds,
                server_settings={"timezone": "UTC", "application_name": "quantbot"},
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
