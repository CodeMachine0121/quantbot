# quantbot/infrastructure/persistence/timescale_candle_repository.py
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import asyncpg
import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.time_range import TimeRange
from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase

# COPY 要的位置式 tuple，順序與 WRITE_COLUMNS 一致
CandleRecord = tuple[
    str, str, str, datetime, float, float, float, float, float, int | None, str
]


class TimescaleCandleRepository:
    """candles 這張 hypertable 的讀寫。實作 domain 的 CandleRepository。

    SQL 只允許出現在這一層。欄位順序是這個類別最重要的資產：COPY 是按位置
    對欄位的，順序錯了不會報錯，只會把 volume 寫進 close——所以順序只寫在
    WRITE_COLUMNS 一份，DDL 與合併語句都從它產生。
    """

    WRITE_COLUMNS: ClassVar[tuple[str, ...]] = (
        "symbol",
        "market",
        "timeframe",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "source",
    )
    READ_COLUMNS: ClassVar[tuple[str, ...]] = (
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
    )
    # 可讀取的表與 view 白名單。表名不能當綁定參數，所以要自己擋住。
    READABLE_TABLES: ClassVar[frozenset[str]] = frozenset(
        {"candles", "candles_5m", "candles_1h"}
    )

    STAGING_DDL: ClassVar[str] = """
    CREATE TEMP TABLE candles_staging
        (LIKE candles INCLUDING DEFAULTS)
        ON COMMIT DROP;
    """
    # DISTINCT ON 是必要的：官方月檔在月份邊界偶爾會有重複列，
    # 而 source 排序讓權威來源在同一批次裡勝出。
    MERGE_SQL: ClassVar[str] = f"""
    INSERT INTO candles ({", ".join(WRITE_COLUMNS)})
    SELECT DISTINCT ON (symbol, market, timeframe, open_time)
           {", ".join(WRITE_COLUMNS)}
    FROM   candles_staging
    ORDER  BY symbol, market, timeframe, open_time, source
    ON CONFLICT (symbol, market, timeframe, open_time) DO NOTHING;
    """

    def __init__(self, database: PostgresDatabase, *, table: str = "candles") -> None:
        if table not in self.READABLE_TABLES:
            raise ValueError(f"不可讀的表：{table}")
        self._database = database
        self._table = table

    async def save(self, series: CandleSeries, *, source: str) -> int:
        """COPY 進暫存表，再一句 INSERT ... ON CONFLICT 併進主表。

        回傳實際新增的列數；已存在的列被主鍵擋掉，所以重跑是安全的。
        """
        records = self._to_records(series, source=source)
        if not records:
            return 0

        pool = await self._database.pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(self.STAGING_DDL)
            await connection.copy_records_to_table(
                "candles_staging",
                records=records,
                columns=list(self.WRITE_COLUMNS),
            )
            status = await connection.execute(self.MERGE_SQL)

        return int(status.rsplit(" ", 1)[-1])  # status 形如 'INSERT 0 43200'

    async def read(self, instrument: Instrument, period: TimeRange) -> CandleSeries:
        rows = await self._fetch(
            f"""
            SELECT {", ".join(self.READ_COLUMNS)}
            FROM   {self._table}
            WHERE  symbol = $1 AND market = $2 AND timeframe = $3
              AND  open_time >= $4 AND open_time < $5
            ORDER  BY open_time
            """,
            instrument,
            period,
        )
        candles = pd.DataFrame(rows, columns=list(self.READ_COLUMNS))
        open_times = pd.to_datetime(candles["open_time"], utc=True)
        open_times.name = CandleColumns.OPEN_TIME
        return CandleSeries(
            instrument, candles.drop(columns=["open_time"]).set_index(open_times)
        )

    async def existing_open_times(
        self, instrument: Instrument, period: TimeRange
    ) -> pd.DatetimeIndex:
        """缺漏偵測只需要索引，不必把整段資料撈出來。"""
        rows = await self._fetch(
            f"""
            SELECT open_time
            FROM   {self._table}
            WHERE  symbol = $1 AND market = $2 AND timeframe = $3
              AND  open_time >= $4 AND open_time < $5
            ORDER  BY open_time
            """,
            instrument,
            period,
        )
        return pd.DatetimeIndex(
            [row["open_time"] for row in rows], tz="UTC", name=CandleColumns.OPEN_TIME
        )

    async def _fetch(
        self, statement: str, instrument: Instrument, period: TimeRange
    ) -> list[asyncpg.Record]:
        pool = await self._database.pool()
        rows: list[asyncpg.Record] = await pool.fetch(
            statement,
            instrument.symbol,
            str(instrument.market),
            instrument.timeframe.value,
            period.start.to_pydatetime(),
            period.end.to_pydatetime(),
        )
        return rows

    def _to_records(self, series: CandleSeries, *, source: str) -> list[CandleRecord]:
        """把 CandleSeries 攤成 COPY 要的位置式 tuple。

        欄位順序在這裡收斂，entity 不需要知道資料庫長什麼樣。
        先轉成 numpy 陣列再組，比逐列 iterrows 快一個數量級，
        而且型別是明確的 float64，不會混進 object。
        """
        instrument = series.instrument
        prices = series.frame[["open", "high", "low", "close", "volume"]].to_numpy(
            dtype="float64"
        )
        trade_counts = series.frame["trade_count"].to_numpy(dtype="object")

        return [
            (
                instrument.symbol,
                str(instrument.market),
                instrument.timeframe.value,
                open_time.to_pydatetime(),
                float(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                None if pd.isna(trade_count) else int(trade_count),
                source,
            )
            for open_time, row, trade_count in zip(
                series.open_times, prices, trade_counts, strict=True
            )
        ]
