# quantbot/domain/dto/recording_report.py
from __future__ import annotations

from dataclasses import dataclass

from quantbot.domain.values.listing import Listing


@dataclass(frozen=True)
class RecordingReportDto:
    """錄製結束後的成績單。

    resynchronization_count 是這份報告裡最該被盯著看的數字。它不是錯誤計數——
    序號斷裂在真實連線上一定會發生。它是**健康指標**：一小時斷兩次是正常的，
    一分鐘斷二十次代表網路或訂閱方式有問題，而如果它永遠是 0，比較可能的解釋是
    序號校驗根本沒有生效，不是連線特別穩。
    """

    listing: Listing
    recorded_trade_count: int
    recorded_depth_row_count: int
    applied_update_count: int
    discarded_update_count: int
    resynchronization_count: int
