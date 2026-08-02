# quantbot/domain/services/source_routing_service.py
from __future__ import annotations

from typing import ClassVar

import pandas as pd

from quantbot.domain.values.source_kind import FetchInstruction, SourceKind
from quantbot.domain.values.time_range import TimeRange


class SourceRoutingService:
    """一段區間該走哪條來源。

    判斷依據只有兩個，而且都跟交易所的實作無關，所以它屬於 domain：
    一是批次檔的上傳延遲（太新的資料只有 REST 有），二是成本（缺口太短的話，
    下載整包 zip 再解壓反而是繞遠路）。

    這個 service 不碰網路、不吃任何介面，所以測試不需要任何替身。
    """

    DEFAULT_UPLOAD_LAG_DAYS: ClassVar[int] = 2
    DEFAULT_MINIMUM_ARCHIVE_SPAN: ClassVar[pd.Timedelta] = pd.Timedelta(days=2)

    def __init__(
        self,
        *,
        upload_lag_days: int = DEFAULT_UPLOAD_LAG_DAYS,
        minimum_archive_span: pd.Timedelta = DEFAULT_MINIMUM_ARCHIVE_SPAN,
    ) -> None:
        self._upload_lag_days = upload_lag_days
        self._minimum_archive_span = minimum_archive_span

    def archive_available_until(self, now: pd.Timestamp) -> pd.Timestamp:
        """這個時間點之後的資料只有 REST 有。

        當日資料隔日上傳、月檔次月初才出現，所以取一個保守的緩衝：
        多抓一天 REST 的成本是兩次請求，少抓一天造成的缺漏要之後才會發現。
        """
        return (now - pd.Timedelta(days=self._upload_lag_days)).normalize()

    def route(
        self, period: TimeRange, *, now: pd.Timestamp
    ) -> tuple[FetchInstruction, ...]:
        """把一段區間切成一到兩個取得指令。"""
        if period.is_empty():
            return ()

        cutoff = self.archive_available_until(now)
        too_new = period.start >= cutoff
        too_short = period.duration < self._minimum_archive_span
        if too_new or too_short:
            return (FetchInstruction(SourceKind.REST, period),)

        archive_period = period.clamp_end(cutoff)
        instructions = [FetchInstruction(SourceKind.ARCHIVE, archive_period)]
        if period.end > cutoff:
            instructions.append(
                FetchInstruction(SourceKind.REST, TimeRange(cutoff, period.end))
            )
        return tuple(instructions)
