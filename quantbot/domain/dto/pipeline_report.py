# quantbot/domain/dto/pipeline_report.py
from dataclasses import dataclass, field

import pandas as pd

from quantbot.domain.dto.data_integrity_report import DataIntegrityReportDto
from quantbot.domain.dto.price_cross_check_report import PriceCrossCheckReportDto
from quantbot.domain.values.instrument import Instrument


@dataclass
class InstrumentReportDto:
    """單一 instrument 這一輪做了什麼、結果如何。"""

    instrument: Instrument
    integrity_before: DataIntegrityReportDto | None = None
    integrity_after: DataIntegrityReportDto | None = None
    written_bar_counts: dict[str, int] = field(default_factory=dict)
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    cross_check: PriceCrossCheckReportDto | None = None
    failure: str | None = None

    @property
    def ok(self) -> bool:
        if self.failure is not None:
            return False
        if self.integrity_after is not None and not self.integrity_after.is_complete:
            return False
        return self.cross_check is None or self.cross_check.passed


@dataclass(frozen=True)
class PipelineReportDto:
    """整輪的報告。exit code 由它決定。"""

    run_at: pd.Timestamp
    instrument_reports: tuple[InstrumentReportDto, ...]

    @property
    def ok(self) -> bool:
        return all(report.ok for report in self.instrument_reports)
