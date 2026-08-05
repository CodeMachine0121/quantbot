# quantbot/infrastructure/reporting/text_imbalance_power_report_renderer.py
from __future__ import annotations

from collections.abc import Sequence

from quantbot.domain.dto.imbalance_power_report import ImbalancePowerReportDto
from quantbot.domain.dto.predictive_power_report import PredictivePowerReportDto


class TextImbalancePowerReportRenderer:
    """把 OBI 的驗證結果印成兩張並排的表。

    每一列都帶樣本數與 t 值，不是只有相關係數。一個 0.08 的相關係數在三千筆樣本上
    跟在三十筆樣本上是完全不同的兩件事，而只印相關係數的報告看不出差別。
    """

    def render(self, report: ImbalancePowerReportDto) -> str:
        lines = [
            f"{report.listing.storage_key}",
            f"  掛單簿取樣 {report.depth_sample_count:,} 筆，"
            f"K 線 {report.bar_count:,} 根",
            "",
            "  原始取樣（每秒一筆，未來報酬用中間價）",
            *self._table(report.native_reports, unit="筆"),
            "",
            "  聚合到 K 線（未來報酬用收盤價）",
            *self._table(report.bar_reports, unit="根"),
        ]
        return "\n".join(lines)

    def _table(
        self, reports: Sequence[PredictivePowerReportDto], *, unit: str
    ) -> list[str]:
        header = (
            f"    {'特徵':<14} {'往後':>6} {'樣本':>8} {'IC':>8} {'t':>7}"
            f" {'頭尾差(bp)':>11}  分組報酬（bp）"
        )
        rows = [header]
        for report in reports:
            buckets = " ".join(
                f"{value * 10_000:>6.2f}" for value in report.bucket_mean_returns
            )
            monotonic = "單調" if report.is_monotonic else "    "
            rows.append(
                f"    {report.feature_name:<14}"
                f" {str(report.horizon) + unit:>6}"
                f" {report.sample_count:>8,}"
                f" {report.information_coefficient:>8.4f}"
                f" {report.t_statistic:>7.2f}"
                f" {report.top_minus_bottom * 10_000:>11.2f}"
                f"  {buckets} {monotonic}"
            )
        return rows
