# quantbot/infrastructure/reporting/text_breakout_statistics_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.breakout_statistics_report import BreakoutStatisticsReportDto
from quantbot.domain.values.breakout_label import BreakoutLabel


class TextBreakoutStatisticsReportRenderer:
    """把真假突破的統計印成幾行。

    順逆行幅度跟守住比例印在一起，因為只有守住比例會被誤讀成勝率。兩個數字擺在
    同一段裡，「62% 守住但守住時只賺一半的幅度」這種形狀才看得出來。
    """

    def render(self, report: BreakoutStatisticsReportDto) -> str:
        held = BreakoutLabel.HELD.value
        failed = BreakoutLabel.FAILED.value
        lines = [
            f"  突破事件 {report.event_count:,} 次，觀察窗 {report.horizon} 根",
            f"  守住 {report.held_count:,} 次（{report.held_ratio:.2%}）、"
            f"被打回來 {report.failed_count:,} 次",
            "",
            "  期間幅度中位數（價格單位）",
            f"    守住：順行 {report.favourable_median[held]:,.2f}、"
            f"逆行 {report.adverse_median[held]:,.2f}",
            f"    打回：順行 {report.favourable_median[failed]:,.2f}、"
            f"逆行 {report.adverse_median[failed]:,.2f}",
            "",
            "  突破當下就觀察得到的量（中位數）",
            f"    {'量':<20}{'守住':>10}{'打回':>10}{'差':>10}",
        ]
        for contrast in report.contrasts:
            lines.append(
                f"    {contrast.name:<20}"
                f"{contrast.held_median:>10.3f}"
                f"{contrast.failed_median:>10.3f}"
                f"{contrast.difference:>10.3f}"
            )
        return "\n".join(lines)
