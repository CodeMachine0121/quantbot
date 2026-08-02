# quantbot/domain/values/source_kind.py
from dataclasses import dataclass
from enum import StrEnum

from quantbot.domain.values.time_range import TimeRange


class SourceKind(StrEnum):
    """行情來源的種類。domain 只知道有這幾種，不知道它們各自怎麼實作。"""

    ARCHIVE = "archive"  # 官方預先打包的批次檔
    REST = "rest"  # 交易所的 REST 端點


@dataclass(frozen=True)
class FetchInstruction:
    """「這一段用這條來源取」。路由的產出，取得端的輸入。"""

    source_kind: SourceKind
    period: TimeRange
