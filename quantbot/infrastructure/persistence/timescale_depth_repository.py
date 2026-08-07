# quantbot/infrastructure/persistence/timescale_depth_repository.py
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import asyncpg
import pandas as pd

from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase


class TimescaleDepthRepository:
    """order_book_depth 這張 hypertable 的讀寫。實作 domain 的 DepthRepository。

    寫入欄位由 DepthColumns 產生，不是手寫的清單。理由是 DepthColumns.LEVELS 一改，
    SQL、DDL 與 entity 三邊都得跟著改，而只要有一邊沒改到，症狀是「某個深度的欄位
    永遠是 NULL」——查得到、跑得動、算出來的掛單不對稱是錯的。
    """

    WRITE_COLUMNS: ClassVar[tuple[str, ...]] = (
        "symbol",
        "market",
        DepthColumns.CAPTURED_AT,
        *DepthColumns.all_columns(),
    )

    STAGING_DDL: ClassVar[str] = """
    CREATE TEMP TABLE order_book_depth_staging
        (LIKE order_book_depth INCLUDING DEFAULTS)
        ON COMMIT DROP;
    """
    MERGE_SQL: ClassVar[str] = f"""
    INSERT INTO order_book_depth ({", ".join(WRITE_COLUMNS)})
    SELECT DISTINCT ON (symbol, market, {DepthColumns.CAPTURED_AT})
           {", ".join(WRITE_COLUMNS)}
    FROM   order_book_depth_staging
    ORDER  BY symbol, market, {DepthColumns.CAPTURED_AT}
    ON CONFLICT (symbol, market, {DepthColumns.CAPTURED_AT}) DO NOTHING;
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def save(self, series: DepthSeries) -> int:
        records = self._to_records(series)
        if not records:
            return 0

        pool = await self._database.pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(self.STAGING_DDL)
            await connection.copy_records_to_table(
                "order_book_depth_staging",
                records=records,
                columns=list(self.WRITE_COLUMNS),
            )
            status = await connection.execute(self.MERGE_SQL)

        return int(status.rsplit(" ", 1)[-1])

    async def read(self, listing: Listing, period: TimeRange) -> DepthSeries:
        columns = (DepthColumns.CAPTURED_AT, *DepthColumns.all_columns())
        pool = await self._database.pool()
        rows: list[asyncpg.Record] = await pool.fetch(
            f"""
            SELECT {", ".join(columns)}
            FROM   order_book_depth
            WHERE  symbol = $1 AND market = $2
              AND  {DepthColumns.CAPTURED_AT} >= $3
              AND  {DepthColumns.CAPTURED_AT} <  $4
            ORDER  BY {DepthColumns.CAPTURED_AT}
            """,
            listing.symbol,
            str(listing.market),
            period.start.to_pydatetime(),
            period.end.to_pydatetime(),
        )
        depth = pd.DataFrame(rows, columns=list(columns))
        captured = pd.to_datetime(depth[DepthColumns.CAPTURED_AT], utc=True)
        captured.name = DepthColumns.CAPTURED_AT
        return DepthSeries(
            listing,
            depth.drop(columns=[DepthColumns.CAPTURED_AT]).set_index(captured),
        )

    @staticmethod
    def _to_records(
        series: DepthSeries,
    ) -> list[tuple[str | datetime | float, ...]]:
        listing = series.listing
        frame = series.frame
        values = frame[list(DepthColumns.all_columns())].to_numpy(dtype="float64")

        return [
            (
                listing.symbol,
                str(listing.market),
                captured_at.to_pydatetime(),
                *(float(value) for value in row),
            )
            for captured_at, row in zip(series.captured_times, values, strict=True)
        ]
