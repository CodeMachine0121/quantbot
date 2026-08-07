# quantbot/application/compare_volume_profiles_application.py
from __future__ import annotations

from quantbot.domain.dto.volume_profile_report import VolumeProfileReportDto
from quantbot.domain.interfaces.candle_repository import CandleRepository
from quantbot.domain.interfaces.trade_repository import TradeRepository
from quantbot.domain.services.volume_profile_service import VolumeProfileService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange


class CompareVolumeProfilesApplication:
    """同一段行情算兩張 profile：逐筆成交精算，與 K 線近似。

    這個用例的產出不是「一張 profile」，是**兩張的差距**。理由是實務上幾乎所有人
    都會用近似版本（逐筆成交算一年要處理兩億多列），所以真正需要知道的不是精算值
    長什麼樣，而是近似值錯多少、以及在什麼情況下錯得比較多。
    """

    def __init__(
        self,
        *,
        candles: CandleRepository,
        trades: TradeRepository,
        service: VolumeProfileService,
    ) -> None:
        self._candles = candles
        self._trades = trades
        self._service = service

    async def run(
        self, instrument: Instrument, period: TimeRange
    ) -> VolumeProfileReportDto:
        listing = Listing.of(instrument)
        candles = await self._candles.read(instrument, period)
        trades = await self._trades.read(listing, period)

        return VolumeProfileReportDto(
            listing=listing,
            trade_row_count=len(trades),
            bar_count=len(candles),
            exact=self._service.from_trades(trades),
            approximate=self._service.from_candles(candles),
        )
