# quantbot/domain/interfaces/depth_repository.py
from typing import Protocol

from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.time_range import TimeRange


class DepthRepository(Protocol):
    """掛單簿深度摘要的持久化。"""

    async def save(self, series: DepthSeries) -> int: ...

    async def read(self, listing: Listing, period: TimeRange) -> DepthSeries: ...
