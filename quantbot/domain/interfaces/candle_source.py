# quantbot/domain/interfaces/candle_source.py
from typing import Protocol

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.time_range import TimeRange


class CandleSource(Protocol):
    """一條行情來源：給我一段區間，還我那段 K 線。

    這是 Protocol 而不是 ABC，所以**實作不需要、也不應該 import 這個檔案**。
    相容性由型別檢查器在組裝的那一點驗證，依賴箭頭因此真的是向內的：
    infrastructure 認識 domain 的形狀，domain 完全不知道 infrastructure 存在。
    """

    async def load(self, instrument: Instrument, period: TimeRange) -> CandleSeries: ...
