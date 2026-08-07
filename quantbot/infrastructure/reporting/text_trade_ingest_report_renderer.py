# quantbot/infrastructure/reporting/text_trade_ingest_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.trade_ingest_report import TradeIngestReportDto


class TextTradeIngestReportRenderer:
    """把逐筆成交回補的報告印成人看得懂的幾行。

    對帳那一段刻意逐欄印出來，而不是只印一個「通過」。九個欄位的誤差並排時，
    欄位對映錯一格會非常明顯——錯的那一欄會是 1e-01 這種量級，其餘是 1e-16。
    只印一個布林值的話，看到的是「失敗」，然後要自己去猜哪裡失敗。
    """

    def render(self, report: TradeIngestReportDto) -> str:
        lines = [
            f"{report.listing.storage_key}",
            f"  抓到 {report.fetched_row_count:,} 列，"
            f"寫入 {report.written_row_count:,} 列（差額是資料庫裡已經有的）",
            f"  成交編號斷號：{report.missing_trade_id_count:,} 筆",
        ]

        agreement = report.agreement
        if agreement is None:
            lines.append("  對帳：沒有資料可比")
            return "\n".join(lines)

        lines.append(
            f"  對帳：{agreement.compared_bar_count:,} 根 K 線，"
            f"容忍度 {agreement.tolerance:.0e}"
        )
        for column, difference in agreement.maximum_relative_difference.items():
            mark = "OK" if difference <= agreement.tolerance else "**"
            lines.append(f"    {mark} {column:<24} 最大相對誤差 {difference:.3e}")
        if agreement.missing_in_rebuilt or agreement.missing_in_official:
            lines.append(
                f"    ** 只有官方有的 {agreement.missing_in_rebuilt} 根，"
                f"只有重建有的 {agreement.missing_in_official} 根"
            )
        lines.append(f"  結果：{'通過' if report.passed else '不通過'}")
        return "\n".join(lines)
