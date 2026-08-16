# quantbot/infrastructure/reporting/text_search_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.search_report import SearchReportDto


class TextSearchReportRenderer:
    """搜尋結果印成一份「先看可信度、再看排名」的報告。

    排版順序是刻意的：試驗次數、剪枝數、雜訊期望上限這三行在最前面，最佳組合的
    排名在後面。順序反過來的話，讀的人會先記住那個漂亮的夏普，而之後看到的每一句
    警告都只是註腳。
    """

    TOP_ROWS = 5

    def render(self, report: SearchReportDto) -> str:
        lines = [
            f"[{report.label}]",
            f"  搜尋空間 {report.unconstrained_combination_count} 種組合，"
            f"剪枝 {report.pruned_count} 種，實際跑 {report.trial_count} 種",
            f"  樣本內 {report.in_sample_bar_count:,} 根 / "
            f"樣本外 {report.out_of_sample_bar_count:,} 根",
            f"  純靠運氣的夏普期望上限 {report.expected_maximum_sharpe:+.3f}"
            f"（{report.trial_count} 次試驗、{report.in_sample_bar_count:,} 根樣本內）",
            "",
            f"  最佳（依樣本內夏普） {report.best_by_in_sample.strategy_name}",
            f"    樣本內夏普 {report.best_in_sample_sharpe:+.3f}"
            f"，扣掉運氣之後 {report.haircut:+.3f}",
            f"    樣本外夏普 "
            f"{self._sharpe(report.best_by_in_sample.out_of_sample_sharpe)}"
            f"，樣本外報酬 {report.best_by_in_sample.out_of_sample_return:+.2%}",
            f"  全部組合的樣本內夏普中位數 {report.median_in_sample_sharpe:+.3f}",
            f"  樣本內為正的組合裡，樣本外也為正的比例 {report.survival_rate:.1%}",
            "",
            f"  樣本內排名前 {self.TOP_ROWS} 名",
            f"    {'組合':<44} {'交易':>5} {'樣本內夏普':>10} {'樣本外夏普':>10}"
            f" {'樣本外報酬':>10}",
        ]
        ranked = sorted(
            (trial for trial in report.trials if trial.in_sample_sharpe is not None),
            key=lambda trial: trial.in_sample_sharpe or 0.0,
            reverse=True,
        )
        for trial in ranked[: self.TOP_ROWS]:
            lines.append(
                f"    {trial.strategy_name:<44} {trial.trade_count:>5}"
                f" {self._sharpe(trial.in_sample_sharpe):>10}"
                f" {self._sharpe(trial.out_of_sample_sharpe):>10}"
                f" {trial.out_of_sample_return:>+10.2%}"
            )
        return "\n".join(lines)

    @staticmethod
    def _sharpe(value: float | None) -> str:
        """算不出夏普時印「沒有定義」而不是 0。

        一個從不交易的策略的夏普不是 0，是沒有定義；印成 0 會讓它排在賠錢的策略
        前面，而那個排名毫無意義。
        """
        return "沒有定義" if value is None else f"{value:+.3f}"
