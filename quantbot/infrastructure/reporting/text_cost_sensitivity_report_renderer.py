# quantbot/infrastructure/reporting/text_cost_sensitivity_report_renderer.py
from __future__ import annotations

from quantbot.domain.dto.cost_sensitivity_report import CostSensitivityReportDto
from quantbot.domain.dto.slippage_estimate_report import SlippageEstimateReportDto


class TextCostSensitivityReportRenderer:
    """費率掃描印成一張表，加上由賺轉賠的位置。

    每一列都印「成本佔毛利」而不是只印總報酬。理由是那個比率回答的是另一個問題：
    總報酬告訴你結果，成本佔毛利告訴你**這個結果是不是被成本決定的**。一個毛利
    +0.89%、成本吃掉 5062% 的策略，跟一個毛利 +50%、成本吃掉 10% 的策略，
    即使淨報酬一樣，要做的事完全不同。
    """

    def render(self, report: CostSensitivityReportDto) -> str:
        lines = [
            f"策略 {report.strategy_name}",
            f"  交易 {report.trade_count} 筆，總換手 {report.turnover:.1f} 倍"
            f"（平均一筆 {report.cost_per_trade_rate:.2f} 倍）",
            f"  未扣成本的總報酬 {report.gross_total_return:+.2%}",
            "",
            f"  {'taker':>8} {'來回':>8} {'總報酬':>10} {'付出成本':>12}"
            f" {'成本佔毛利':>12}",
        ]
        for row in report.rows:
            share = (
                f"{row.cost_share_of_gross_profit:>11.1%}"
                if row.cost_share_of_gross_profit is not None
                else f"{'毛利為負':>10}"
            )
            lines.append(
                f"  {row.taker_fee_rate:>8.4%} {row.round_trip_rate:>8.3%}"
                f" {row.total_return:>+10.2%} {row.cost_paid:>12,.0f} {share}"
            )

        lines.append("")
        if report.break_even_round_trip_rate is None:
            lines.append(
                "  由賺轉賠的位置：不在這個網格內"
                "（最低的成本假設下就已經賠錢，或最高的假設下還在賺）"
            )
        else:
            lines.append(
                f"  由賺轉賠的來回成本率 {report.break_even_round_trip_rate:.4%}"
                f"（線性內插）"
            )
        return "\n".join(lines)

    def render_slippage(self, report: SlippageEstimateReportDto | None) -> str:
        if report is None:
            return (
                "掛單簿滑價估計：這段期間沒有錄到掛單簿。\n"
                "  沿用假設值，而且它是假設——NEVER 因為沒有資料就當成沒有滑價。"
            )
        # 用基點（1 bp = 0.01%）而不是百分比：BTC/USDT 現貨的價差是一個 tick，
        # 相對值小到用百分比印會變成一整排 0.00%
        return "\n".join(
            [
                f"掛單簿滑價估計（{report.sample_count:,} 筆取樣，"
                f"涵蓋 {report.covered_hours:.1f} 小時）",
                f"  半價差 中位數 {report.median_half_spread_rate * 10_000:.5f} bp"
                f"、平均 {report.mean_half_spread_rate * 10_000:.5f} bp"
                f"、95 百分位 {report.percentile95_half_spread_rate * 10_000:.5f} bp",
                f"  前五檔買方名目 中位數 {report.median_top_5_notional:,.0f}"
                f"，這次要下的單 {report.order_notional:,.0f}"
                f"（{'吃不完' if report.order_fits_in_top_5 else '吃得完'}）",
                f"  建議的滑價假設 {report.suggested_slippage_rate * 10_000:.5f} bp"
                f"（= {report.suggested_slippage_rate:.7%}）",
                "  注意：這只涵蓋滑價的價差那一部分。延遲造成的滑價要實單才量得到，"
                "而市場衝擊在這個單量下可以忽略（見上面那一行）。",
            ]
        )
