# quantbot/infrastructure/reporting/text_backtest_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.backtest_report import BacktestReportDto


class TextBacktestReportRenderer:
    """一份回測結果印成幾行字。

    **試驗次數印在第一行。** 一個「試了 500 個組合挑出來的最佳結果」與一個
    「只跑了一次的結果」，數字看起來一樣但可信度差好幾個數量級，而看報告的人
    沒辦法從報酬率反推出那件事。所以它不能是附註。

    毛利與淨利並排印。只印其中一個的話，「這個策略不賺錢」與「這個策略賺的錢
    全被成本吃掉」看起來一樣，而兩者要做的事完全不同——前者要改策略，
    後者要降低交易頻率。
    """

    def render(self, report: BacktestReportDto) -> str:
        lines = [
            f"策略 {report.strategy_name}（試驗次數 {report.trial_count}）",
            f"  成本模型  {report.costs.describe()}",
            f"  K 線 {report.bar_count:,} 根，交易 {report.trade_count} 筆，"
            f"曝險 {report.exposure:.2%}",
            f"  總報酬  {report.total_return:>+9.2%}"
            f"（未扣成本 {report.gross_total_return:>+9.2%}）",
            f"  期末權益 {report.final_equity:>12,.2f}"
            f"（起始 {report.initial_capital:,.2f}）",
            f"  付出成本 {report.cost_paid:>12,.2f}，總換手 {report.turnover:.1f} 倍",
        ]
        share = report.cost_share_of_gross_profit
        lines.append(
            f"  成本佔毛利 {share:.2%}"
            if share is not None
            else "  成本佔毛利  毛利為負，這個比率沒有意義"
        )
        if not report.trades.empty:
            lines.append(
                f"  單筆持有 中位數 {report.trades['bars_held'].median():.0f} 根，"
                f"最長 {report.trades['bars_held'].max():.0f} 根"
            )
        return "\n".join(lines)
