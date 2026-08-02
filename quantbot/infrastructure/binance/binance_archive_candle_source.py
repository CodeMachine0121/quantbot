# quantbot/infrastructure/binance/binance_archive_candle_source.py
from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.interfaces.candle_parser import CandleParser
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.time_range import TimeRange
from quantbot.infrastructure.binance.binance_archive_downloader import (
    BinanceArchiveDownloader,
)
from quantbot.infrastructure.binance.binance_archive_url_builder import (
    BinanceArchiveUrlBuilder,
)


class BinanceArchiveCandleSource:
    """data.binance.vision 這條來源。實作 domain 的 CandleSource。

    「月檔還是日檔」完全是這個類別的內務：domain 只說「這段走批次」，
    要下載哪幾個檔、怎麼併發、哪些檔還不存在，由這裡決定。
    """

    def __init__(
        self,
        downloader: BinanceArchiveDownloader,
        url_builder: BinanceArchiveUrlBuilder,
        parser: CandleParser,
    ) -> None:
        self._downloader = downloader
        self._url_builder = url_builder
        self._parser = parser

    async def load(self, instrument: Instrument, period: TimeRange) -> CandleSeries:
        urls = self._archive_urls(instrument, period)
        payloads = await asyncio.gather(
            *(self._downloader.download(url) for url in urls)
        )

        # 解壓與解析是 CPU 使用密集的，丟到執行緒池，不要阻塞事件迴圈
        frames = await asyncio.gather(
            *(
                asyncio.to_thread(self._parser.parse, payload)
                for payload in payloads
                if payload is not None
            )
        )
        if not frames:
            return CandleSeries.empty(instrument)

        combined = pd.concat(frames).sort_index()
        series = CandleSeries(
            instrument, combined[~combined.index.duplicated(keep="first")]
        )
        return series.restricted_to(period)

    def _archive_urls(self, instrument: Instrument, period: TimeRange) -> list[str]:
        """先用完整月份的月檔，月檔蓋不到的零頭用日檔補。"""
        months = self._complete_months(period)
        covered = {
            day.date()
            for month in months
            for day in pd.date_range(
                pd.Timestamp(month), pd.Timestamp(month) + pd.offsets.MonthEnd(0)
            )
        }
        leftover_days = [
            day.date()
            for day in pd.date_range(
                period.start.normalize(), period.end, inclusive="left", freq="D"
            )
            if day.date() not in covered
        ]

        return [self._url_builder.monthly(instrument, month) for month in months] + [
            self._url_builder.daily(instrument, day) for day in leftover_days
        ]

    @staticmethod
    def _complete_months(period: TimeRange) -> list[date]:
        """完整落在區間內的月份。半個月的月檔會多帶到區間外的資料，所以不用。"""
        months: list[date] = []
        cursor = period.start.normalize().replace(day=1)
        while cursor < period.end:
            month_end = cursor + pd.offsets.MonthEnd(0)
            if cursor >= period.start.normalize() and month_end < period.end:
                months.append(cursor.date())
            cursor = cursor + pd.offsets.MonthBegin(1)
        return months
