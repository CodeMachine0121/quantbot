# quantbot/infrastructure/reporting/text_pipeline_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.pipeline_report import InstrumentReportDto, PipelineReportDto


class TextPipelineReportRenderer:
    """把報告 DTO 印成給人看的文字。

    渲染是輸出格式，屬於 infrastructure。哪天要改成 JSON 給 Grafana 吃、
    或改成 Markdown 貼進 Telegram，多寫一個 renderer 就好，
    application 與 DTO 一個字都不用改。
    """

    def render(self, report: PipelineReportDto) -> str:
        lines = [
            "=== quantbot data integrity report ===",
            f"run_at : {report.run_at.isoformat()}",
            "",
        ]
        for instrument_report in report.instrument_reports:
            lines.extend(self._render_instrument(instrument_report))
            lines.append("")

        failed = sum(1 for one in report.instrument_reports if not one.ok)
        lines.append(f"result : {'PASS' if report.ok else 'FAIL'}（{failed} 個未通過）")
        lines.append(f"exit   : {0 if report.ok else 1}")
        return "\n".join(lines)

    def _render_instrument(self, report: InstrumentReportDto) -> list[str]:
        lines = [report.instrument.storage_key]
        if report.failure is not None:
            return [*lines, f"  失敗           {report.failure}"]

        before, after = report.integrity_before, report.integrity_after
        if before is not None:
            lines.append(
                f"  預期 / 實際    {before.expected_bar_count:,} / "
                f"{before.actual_bar_count:,}   ({before.coverage_ratio:.2%})"
            )
            lines.append(
                f"  回補前缺口     {len(before.gaps)} 段, "
                f"共 {before.missing_bar_count} 根"
            )
        written = " / ".join(
            f"{source} {count}"
            for source, count in sorted(report.written_bar_counts.items())
        )
        lines.append(f"  本次寫入       {written or '無'}")
        if after is not None:
            lines.append(f"  回補後缺口     {len(after.gaps)} 段")
        if report.anomaly_counts:
            anomalies = " / ".join(
                f"{flag} {count}"
                for flag, count in sorted(report.anomaly_counts.items())
            )
            lines.append(f"  異常標記       {anomalies}")
        if report.cross_check is not None:
            check = report.cross_check
            lines.append(
                f"  對照組 {check.reference_name}（容許 {check.tolerance:.2%}）"
                f"    最大相對差 {check.maximum_relative_difference:.2%}"
                f"    {'PASS' if check.passed else 'FAIL  需人工確認'}"
            )
        else:
            lines.append("  對照組         SKIP（這個交易對沒有對照來源）")
        return lines
