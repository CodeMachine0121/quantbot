# quantbot/domain/values/listing.py
from __future__ import annotations

from dataclasses import dataclass

from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market


@dataclass(frozen=True)
class Listing:
    """一個交易對在某個市場上的掛牌：symbol ＋ market，沒有粒度。

    逐筆成交與掛單簿沒有 timeframe——它們是事件，不是被切好的區間。所以它們的
    身分不能用 Instrument 表示，硬塞一個 timeframe 進去只會讓「這段 tick 是 1m
    的」這種沒有意義的句子變成合法的程式碼。

    Instrument 因此可以看成 Listing ＋ timeframe，用 Listing.of() 取得那一半。
    """

    symbol: str  # ccxt 寫法，帶斜線：BTC/USDT
    market: Market

    @classmethod
    def of(cls, instrument: Instrument) -> Listing:
        """從 Instrument 取出不含粒度的那一半。"""
        return cls(symbol=instrument.symbol, market=instrument.market)

    @property
    def native_symbol(self) -> str:
        """交易所原生寫法，沒有斜線：BTCUSDT。"""
        return self.symbol.replace("/", "").upper()

    @property
    def storage_key(self) -> str:
        """落地檔名與報告標題的前綴，例如 spot_BTCUSDT。"""
        return f"{self.market}_{self.native_symbol}"
