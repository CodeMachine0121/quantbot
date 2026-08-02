# quantbot/infrastructure/binance/binance_candle_csv_parser.py
from __future__ import annotations

import io
import zipfile
from typing import ClassVar

import pandas as pd

from quantbot.domain.values.candle_columns import CandleColumns


class BinanceCandleCsvParser:
    """把批次 zip 解成一張 K 線的表。實作 domain 的 CandleParser。

    「第幾欄是什麼」是這個類別獨有的知識。官方 CSV 沒有標頭，順序只能查文件，
    而順序錯了不會報錯，只會安靜地把成交筆數當成價格用——所以它關在這裡一份。

    解壓與解析都是 CPU 使用密集的，呼叫端要用 asyncio.to_thread 丟出事件迴圈。
    """

    # 12 欄，順序來自 Binance public data 文件。最後一欄 ignore 官方保留不用，
    # 但它佔一個位置，少算一欄後面全錯。
    COLUMN_ORDER: ClassVar[tuple[str, ...]] = (
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    )

    def parse(self, payload: bytes) -> pd.DataFrame:
        raw = self._extract_single_csv(payload)
        candles = pd.read_csv(
            io.BytesIO(raw),
            header=None,
            names=list(self.COLUMN_ORDER),
            skiprows=1 if self._has_header_row(raw) else 0,
        )
        open_times = CandleColumns.to_utc(candles["open_time"])
        open_times.name = CandleColumns.OPEN_TIME
        return CandleColumns.conform(candles.set_index(open_times))

    @staticmethod
    def _extract_single_csv(payload: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.read(archive.namelist()[0])

    @staticmethod
    def _has_header_row(raw: bytes) -> bool:
        """2025 年起的檔案多了一行標頭。

        用「第一格是不是數字」偵測，不寫死年份——格式再改一次也不用改判斷邏輯。
        """
        first_cell = raw[: raw.find(b",")].decode("utf-8", errors="ignore").strip()
        return not first_cell.lstrip("-").isdigit()
