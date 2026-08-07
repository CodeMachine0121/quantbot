# quantbot/infrastructure/binance/binance_archive_url_builder.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import ClassVar

from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market


class BinanceArchiveUrlBuilder:
    """data.binance.vision 的網址規則。

    現貨與永續的前綴不同，這裡就把它們隔開。這是 Binance 的細節，
    NEVER 出現在 domain——換一家交易所時，要改的只有這個檔案與它的鄰居。
    """

    BASE_URL: ClassVar[str] = "https://data.binance.vision/data"
    MARKET_PREFIXES: ClassVar[Mapping[Market, str]] = MappingProxyType(
        {
            Market.SPOT: "spot",
            Market.USD_MARGINED_PERPETUAL: "futures/um",
        }
    )

    def monthly(self, instrument: Instrument, month: date) -> str:
        return self._archive_url(instrument, "monthly", f"{month:%Y-%m}")

    def daily(self, instrument: Instrument, day: date) -> str:
        """月檔還沒出來的那幾天用日檔補。"""
        return self._archive_url(instrument, "daily", f"{day:%Y-%m-%d}")

    def daily_agg_trades(self, listing: Listing, day: date) -> str:
        """逐筆成交只有日檔這條路。

        月檔存在，但 BTC/USDT 現貨一個月的 aggTrades zip 接近 500 MB，而要分析的
        通常是幾天，所以這裡不提供 monthly_agg_trades()——**沒有這個方法本身就是
        設計決定**，不是還沒寫。要一個月的話就下三十個日檔，併發下載本來就有。

        網址裡沒有 timeframe：成交是事件，不是被切好的區間，所以它吃 Listing。
        """
        prefix = self.MARKET_PREFIXES[listing.market]
        symbol = listing.native_symbol
        filename = f"{symbol}-aggTrades-{day:%Y-%m-%d}.zip"
        return f"{self.BASE_URL}/{prefix}/daily/aggTrades/{symbol}/{filename}"

    @staticmethod
    def checksum(archive_url: str) -> str:
        """每個 zip 旁邊都有一份同名加 .CHECKSUM 的官方雜湊。"""
        return f"{archive_url}.CHECKSUM"

    def _archive_url(self, instrument: Instrument, period: str, stamp: str) -> str:
        prefix = self.MARKET_PREFIXES[instrument.market]
        symbol = instrument.native_symbol
        timeframe = instrument.timeframe
        filename = f"{symbol}-{timeframe}-{stamp}.zip"
        return (
            f"{self.BASE_URL}/{prefix}/{period}/klines/{symbol}/{timeframe}/{filename}"
        )
