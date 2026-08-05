# quantbot/domain/dto/imbalance_power_report.py
from __future__ import annotations

from dataclasses import dataclass

from quantbot.domain.dto.predictive_power_report import PredictivePowerReportDto
from quantbot.domain.values.listing import Listing


@dataclass(frozen=True)
class ImbalancePowerReportDto:
    """OBI 的驗證結果，分成兩組。

    兩組並排是這份報告的重點。原始取樣（每秒一筆）與聚合到 K 線之後的結果如果
    差很多，那個差距本身就是結論：它說明這個特徵的資訊藏在秒級，而不是在
    「這一分鐘平均起來偏哪一邊」。只看其中一組會得到相反的判斷。
    """

    listing: Listing
    depth_sample_count: int
    bar_count: int
    native_reports: tuple[PredictivePowerReportDto, ...]
    bar_reports: tuple[PredictivePowerReportDto, ...]
