# quantbot/infrastructure/binance/binance_archive_trade_source.py
from __future__ import annotations

import asyncio

import pandas as pd

from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.interfaces.trade_parser import TradeParser
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange
from quantbot.infrastructure.binance.binance_archive_downloader import (
    BinanceArchiveDownloader,
)
from quantbot.infrastructure.binance.binance_archive_url_builder import (
    BinanceArchiveUrlBuilder,
)


class BinanceArchiveTradeSource:
    """data.binance.vision 的 aggTrades 這條來源。實作 domain 的 TradeSource。

    跟 Day 03 的 BinanceArchiveCandleSource 有一個刻意的差別：**這裡只用日檔，
    不用月檔。** K 線那邊優先抓月檔是對的，一個月的 1 分鐘 K 線壓縮後只有幾十 KB，
    少幾個請求就是省。aggTrades 完全相反——BTC/USDT 現貨一個月的 zip 接近 500 MB，
    而實際要分析的通常是幾天。用日檔（一天約 11 MB）換來的是：想要幾天就下幾天、
    快取有意義、中斷重跑的代價是一天而不是一個月。

    這是「同一條路徑」跟「同一份程式碼」的差別。路徑相同（官方批次 zip、驗
    checksum、快取、解壓解析），但檔案粒度的取捨由資料的體積決定，NEVER 因為
    K 線那邊那樣寫就照抄。
    """

    def __init__(
        self,
        downloader: BinanceArchiveDownloader,
        url_builder: BinanceArchiveUrlBuilder,
        parser: TradeParser,
    ) -> None:
        self._downloader = downloader
        self._url_builder = url_builder
        self._parser = parser

    async def load(self, listing: Listing, period: TimeRange) -> TradeSeries:
        urls = [
            self._url_builder.daily_agg_trades(listing, day.date())
            for day in pd.date_range(
                period.start.normalize(), period.end, inclusive="left", freq="D"
            )
        ]
        payloads = await asyncio.gather(
            *(self._downloader.download(url) for url in urls)
        )

        frames = await asyncio.gather(
            *(
                asyncio.to_thread(self._parser.parse, payload)
                for payload in payloads
                if payload is not None
            )
        )
        if not frames:
            return TradeSeries.empty(listing)

        combined = pd.concat(frames)
        # 去重看 trade_id 而不是索引：同一個時間戳有幾十筆成交是常態
        deduplicated = combined[~combined["trade_id"].duplicated(keep="first")]
        return TradeSeries(listing, deduplicated).restricted_to(period)
