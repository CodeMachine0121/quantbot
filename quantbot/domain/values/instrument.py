# quantbot/domain/values/instrument.py
from dataclasses import dataclass

from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe


@dataclass(frozen=True)
class Instrument:
    """要處理的是哪一段行情：交易對、市場、粒度。

    market 沒有預設值，型別也不是字串：現貨與永續 NEVER 混用這條規矩，靠的是
    「不合法的組合連物件都建不出來」，不是靠註解提醒。

    網址規則不在這裡。那是 data.binance.vision 的細節，屬於 infrastructure；
    這個值只描述「哪一段行情」，換一家交易所它一個字都不用改。
    """

    symbol: str  # ccxt 寫法，帶斜線：BTC/USDT
    market: Market
    timeframe: Timeframe

    @property
    def native_symbol(self) -> str:
        """交易所原生寫法，沒有斜線：BTCUSDT。轉換只寫在這裡一份。"""
        return self.symbol.replace("/", "").upper()

    @property
    def storage_key(self) -> str:
        """落地檔名與報告標題的前綴，例如 spot_BTCUSDT_1m。

        market 在鍵值裡，所以現貨與永續從落地那一刻就是兩個檔案。
        """
        return f"{self.market}_{self.native_symbol}_{self.timeframe}"
