# quantbot/domain/dto/trade_ingest_report.py
from __future__ import annotations

from dataclasses import dataclass

from quantbot.domain.dto.candle_agreement_report import CandleAgreementReportDto
from quantbot.domain.values.listing import Listing


@dataclass(frozen=True)
class TradeIngestReportDto:
    """一次逐筆成交回補的結果。

    written_row_count 跟 fetched_row_count 分開列，因為它們不相等才是正常的：
    重跑同一天，抓到的還是七十幾萬列，寫進去的是 0。兩個數字都印出來，
    「重跑沒事」這件事才看得見，而不是要去猜。
    """

    listing: Listing
    fetched_row_count: int
    written_row_count: int
    missing_trade_id_count: int
    agreement: CandleAgreementReportDto | None = None

    @property
    def passed(self) -> bool:
        return (
            self.fetched_row_count > 0
            and self.missing_trade_id_count == 0
            and self.agreement is not None
            and self.agreement.passed
        )
