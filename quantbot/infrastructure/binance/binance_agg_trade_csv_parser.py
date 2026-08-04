# quantbot/infrastructure/binance/binance_agg_trade_csv_parser.py
from __future__ import annotations

import io
import zipfile
from typing import ClassVar

import pandas as pd

from quantbot.domain.values.trade_columns import TradeColumns


class BinanceAggTradeCsvParser:
    """把 aggTrades 批次 zip 解成一張逐筆成交的表。實作 domain 的 TradeParser。

    七欄，順序來自 Binance public data 文件。跟 K 線那份不同的是這裡沒有 ignore 欄，
    但多了兩個識別碼，而且 is_best_match 這一欄我們不留——它描述的是撮合當下的
    技術細節，對特徵計算沒有用，留著只會讓每一天多幾 MB。

    一天的 BTC/USDT 現貨 aggTrades 是七十幾萬列、解壓後 60 MB 上下，所以解析同樣
    要用 asyncio.to_thread 丟出事件迴圈，而且 NEVER 一次讀一個月——月檔接近 500 MB。
    """

    COLUMN_ORDER: ClassVar[tuple[str, ...]] = (
        "trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "transact_time",
        "buyer_is_maker",
        "is_best_match",
    )
    BOOLEAN_TEXT: ClassVar[dict[str, bool]] = {
        "True": True,
        "true": True,
        "False": False,
        "false": False,
    }

    def parse(self, payload: bytes) -> pd.DataFrame:
        raw = self._extract_single_csv(payload)
        trades = pd.read_csv(
            io.BytesIO(raw),
            header=None,
            names=list(self.COLUMN_ORDER),
            skiprows=1 if self._has_header_row(raw) else 0,
            dtype={"buyer_is_maker": "string"},
        )
        transact_times = TradeColumns.to_utc(trades[TradeColumns.TRANSACT_TIME])
        transact_times.name = TradeColumns.TRANSACT_TIME
        trades[TradeColumns.BUYER_IS_MAKER] = (
            trades[TradeColumns.BUYER_IS_MAKER].str.strip().map(self.BOOLEAN_TEXT)
        )
        return TradeColumns.conform(trades.set_index(transact_times))

    @staticmethod
    def _extract_single_csv(payload: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.read(archive.namelist()[0])

    @staticmethod
    def _has_header_row(raw: bytes) -> bool:
        """跟 K 線那支一樣用「第一格是不是數字」判斷，不寫死年份。"""
        first_cell = raw[: raw.find(b",")].decode("utf-8", errors="ignore").strip()
        return not first_cell.lstrip("-").isdigit()
