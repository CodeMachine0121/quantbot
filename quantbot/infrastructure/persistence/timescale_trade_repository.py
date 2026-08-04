# quantbot/infrastructure/persistence/timescale_trade_repository.py
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import asyncpg
import pandas as pd

from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.trade_columns import TradeColumns
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase

# COPY 要的位置式 tuple，順序與 WRITE_COLUMNS 一致
TradeRecord = tuple[str, str, int, datetime, float, float, int, int, bool, str]


class TimescaleTradeRepository:
    """agg_trades 這張 hypertable 的讀寫。實作 domain 的 TradeRepository。

    跟 Day 07 的 K 線 repository 是同一個形狀（COPY 進暫存表再合併），差別在量級：
    一天七十幾萬列。這讓兩件事從「無所謂」變成「必須」——批次寫入不能逐列 INSERT，
    以及讀取一定要帶時間範圍，NEVER 提供「把這個交易對的成交全撈出來」的方法。
    """

    WRITE_COLUMNS: ClassVar[tuple[str, ...]] = (
        "symbol",
        "market",
        "trade_id",
        "transact_time",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "buyer_is_maker",
        "source",
    )
    READ_COLUMNS: ClassVar[tuple[str, ...]] = (
        "transact_time",
        "trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "buyer_is_maker",
    )

    STAGING_DDL: ClassVar[str] = """
    CREATE TEMP TABLE agg_trades_staging
        (LIKE agg_trades INCLUDING DEFAULTS)
        ON COMMIT DROP;
    """
    MERGE_SQL: ClassVar[str] = f"""
    INSERT INTO agg_trades ({", ".join(WRITE_COLUMNS)})
    SELECT DISTINCT ON (symbol, market, transact_time, trade_id)
           {", ".join(WRITE_COLUMNS)}
    FROM   agg_trades_staging
    ORDER  BY symbol, market, transact_time, trade_id, source
    ON CONFLICT (symbol, market, transact_time, trade_id) DO NOTHING;
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def save(self, series: TradeSeries, *, source: str) -> int:
        records = self._to_records(series, source=source)
        if not records:
            return 0

        pool = await self._database.pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(self.STAGING_DDL)
            await connection.copy_records_to_table(
                "agg_trades_staging",
                records=records,
                columns=list(self.WRITE_COLUMNS),
            )
            status = await connection.execute(self.MERGE_SQL)

        return int(status.rsplit(" ", 1)[-1])

    async def read(self, listing: Listing, period: TimeRange) -> TradeSeries:
        pool = await self._database.pool()
        rows: list[asyncpg.Record] = await pool.fetch(
            f"""
            SELECT {", ".join(self.READ_COLUMNS)}
            FROM   agg_trades
            WHERE  symbol = $1 AND market = $2
              AND  transact_time >= $3 AND transact_time < $4
            ORDER  BY transact_time, trade_id
            """,
            listing.symbol,
            str(listing.market),
            period.start.to_pydatetime(),
            period.end.to_pydatetime(),
        )
        trades = pd.DataFrame(rows, columns=list(self.READ_COLUMNS))
        transact_times = pd.to_datetime(trades["transact_time"], utc=True)
        transact_times.name = TradeColumns.TRANSACT_TIME
        return TradeSeries(
            listing,
            trades.drop(columns=["transact_time"]).set_index(transact_times),
        )

    async def latest_trade_id(self, listing: Listing) -> int | None:
        """已經存到哪一筆。

        走的是 agg_trades_trade_id_index，而不是掃時間範圍：即時串流啟動時要問
        這個問題，那時候還不知道該看哪一段時間。
        """
        pool = await self._database.pool()
        value = await pool.fetchval(
            """
            SELECT max(trade_id)
            FROM   agg_trades
            WHERE  symbol = $1 AND market = $2
            """,
            listing.symbol,
            str(listing.market),
        )
        return None if value is None else int(value)

    @staticmethod
    def _to_records(series: TradeSeries, *, source: str) -> list[TradeRecord]:
        """把整段成交攤成 COPY 要的位置式 tuple。

        先轉 numpy 再組，不用 iterrows：七十幾萬列的差別是幾十秒對幾百毫秒。
        """
        listing = series.listing
        frame = series.frame
        numbers = frame[[TradeColumns.PRICE, TradeColumns.QUANTITY]].to_numpy(
            dtype="float64"
        )
        identifiers = frame[
            [
                TradeColumns.TRADE_ID,
                TradeColumns.FIRST_TRADE_ID,
                TradeColumns.LAST_TRADE_ID,
            ]
        ].to_numpy(dtype="int64")
        buyer_is_maker = frame[TradeColumns.BUYER_IS_MAKER].to_numpy(dtype="bool")

        return [
            (
                listing.symbol,
                str(listing.market),
                int(identifier[0]),
                transact_time.to_pydatetime(),
                float(number[0]),
                float(number[1]),
                int(identifier[1]),
                int(identifier[2]),
                bool(maker),
                source,
            )
            for transact_time, identifier, number, maker in zip(
                series.transact_times,
                identifiers,
                numbers,
                buyer_is_maker,
                strict=True,
            )
        ]
