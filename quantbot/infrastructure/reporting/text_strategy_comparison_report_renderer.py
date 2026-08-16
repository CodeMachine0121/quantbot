# quantbot/infrastructure/reporting/text_strategy_comparison_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.performance_summary import PerformanceSummaryDto
from quantbot.domain.dto.strategy_comparison_report import StrategyComparisonReportDto


class TextStrategyComparisonReportRenderer:
    """幾個策略並排成一張績效矩陣，加上相關性與基準。

    表格的欄位順序是刻意的：**總報酬排在中間而不是第一欄。** 第一欄放交易筆數與
    曝險，因為它們決定後面每一個數字有多可信；總報酬旁邊一定接著最大回撤，因為
    「賺多少」與「路上要忍受多深」是同一件事的兩面。

    基準單獨印一列在最下面，而每一個策略都印「贏過基準幾個百分點」。贏不過基準的
    策略沒有存在的理由——那些條件只是在製造手續費。
    """

    def render(self, report: StrategyComparisonReportDto) -> str:
        lines = [
            f"並排比較（{report.period_label}）",
            f"  {'策略':<26} {'試驗':>4} {'交易':>5} {'曝險':>7} {'總報酬':>9}"
            f" {'最大回撤':>9} {'最長回撤':>9} {'夏普':>7} {'索提諾':>7}"
            f" {'勝率':>7} {'賠率':>6} {'超額':>9}",
        ]
        for summary in report.ranked_by_sharpe():
            lines.append(self._row(summary, report.baseline))
        lines.append(self._row(report.baseline, report.baseline))

        beating = report.beating_the_baseline()
        lines.extend(
            [
                "",
                f"  贏過基準的策略：{len(beating)} / {len(report.summaries)}",
            ]
        )

        pair = report.most_correlated_pair
        if pair is not None:
            lines.append(
                f"  相關性最高的一對：{pair[0]} 與 {pair[1]}，相關係數 {pair[2]:+.2f}"
            )
            if pair[2] > 0.7:
                lines.append("  注意：這兩個高度相關，同時上線等於把同一個賭注下兩倍。")
        return "\n".join(lines)

    def render_correlation(self, report: StrategyComparisonReportDto) -> str:
        names = list(report.correlation.index)
        widths = max(len(name) for name in names)
        lines = ["相關性矩陣（只算兩邊都有部位的那些根）"]
        header = " " * (widths + 4) + " ".join(
            f"{index:>7}" for index in range(len(names))
        )
        lines.append(header)
        for index, name in enumerate(names):
            values = " ".join(
                self._correlation_cell(report.correlation.loc[name, other])
                for other in names
            )
            lines.append(f"  {index}: {name:<{widths}} {values}")
        return "\n".join(lines)

    def _row(
        self, summary: PerformanceSummaryDto, baseline: PerformanceSummaryDto
    ) -> str:
        excess = summary.excess_over(baseline)
        return (
            f"  {summary.strategy_name:<26} {summary.trial_count:>4}"
            f" {summary.trade_count:>5} {summary.exposure:>7.2%}"
            f" {summary.total_return:>+9.2%} {summary.maximum_drawdown:>+9.2%}"
            f" {summary.longest_drawdown_bars:>9,}"
            f" {self._number(summary.sharpe_ratio):>7}"
            f" {self._number(summary.sortino_ratio):>7}"
            f" {self._percent(summary.win_rate):>7}"
            f" {self._number(summary.payoff_ratio, digits=2):>6}"
            f" {excess:>+9.2%}"
        )

    @staticmethod
    def _number(value: float | None, *, digits: int = 2) -> str:
        return "——" if value is None else f"{value:+.{digits}f}"

    @staticmethod
    def _percent(value: float | None) -> str:
        return "——" if value is None else f"{value:.1%}"

    @staticmethod
    def _correlation_cell(value: float) -> str:
        """NaN 印成兩個破折號而不是 0.00。

        「沒有重疊的部位所以算不出來」與「完全不相關」是兩件事，而後者是一個
        很強的結論，不該由缺資料產生。
        """
        return "     ——" if value != value else f"{value:>+7.2f}"
