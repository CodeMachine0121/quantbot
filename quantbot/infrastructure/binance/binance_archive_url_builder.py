# quantbot/infrastructure/binance/binance_archive_url_builder.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import ClassVar

from quantbot.domain.values.instrument import Instrument
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
