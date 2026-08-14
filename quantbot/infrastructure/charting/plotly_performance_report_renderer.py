# quantbot/infrastructure/charting/plotly_performance_report_renderer.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.dto.strategy_comparison_report import StrategyComparisonReportDto


class PlotlyPerformanceReportRenderer:
    """單一策略的一頁式報告，以及多策略的比較視圖。

    一頁式報告有四格，而它們的順序對應「讀一份績效報告的順序」：先看權益曲線
    （整體形狀），再看回撤（痛的部分），再看月報酬（穩不穩定），最後看單筆交易的
    分布（賺賠的結構）。

    回撤畫在權益曲線下面而不是疊在上面，因為它的單位不同（百分比 vs 金額）。
    但兩格共用時間軸，所以「哪一段在回撤」對得回權益曲線上的哪一段。
    """

    def render(
        self,
        report: BacktestReportDto,
        monthly_returns: pd.Series,
        *,
        baseline: BacktestReportDto | None = None,
    ) -> go.Figure:
        figure = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.08,
            row_heights=[0.34, 0.2, 0.24, 0.22],
            subplot_titles=(
                f"權益曲線（試驗次數 {report.trial_count}、"
                f"{report.trade_count} 筆交易、曝險 {report.exposure:.1%}）",
                "回撤（%）",
                "月報酬（%）",
                "單筆交易的淨報酬分布（%）",
            ),
        )

        figure.add_trace(
            go.Scatter(
                x=report.equity.index,
                y=report.equity.to_numpy(),
                mode="lines",
                name=report.strategy_name,
            ),
            row=1,
            col=1,
        )
        if baseline is not None:
            figure.add_trace(
                go.Scatter(
                    x=baseline.equity.index,
                    y=baseline.equity.to_numpy(),
                    mode="lines",
                    name="BuyAndHold 基準",
                    line={"dash": "dash"},
                ),
                row=1,
                col=1,
            )

        drawdown = report.equity / report.equity.cummax() - 1.0
        figure.add_trace(
            go.Scatter(
                x=drawdown.index,
                y=(drawdown * 100.0).to_numpy(),
                mode="lines",
                name="回撤",
                fill="tozeroy",
            ),
            row=2,
            col=1,
        )

        figure.add_trace(
            go.Bar(
                x=monthly_returns.index,
                y=(monthly_returns * 100.0).to_numpy(),
                name="月報酬",
            ),
            row=3,
            col=1,
        )

        if not report.trades.empty:
            figure.add_trace(
                go.Histogram(
                    x=(report.trades["net_return"] * 100.0).to_numpy(),
                    name="單筆淨報酬",
                    nbinsx=40,
                ),
                row=4,
                col=1,
            )

        figure.update_layout(
            title=f"{report.strategy_name}：一頁式績效報告",
            showlegend=True,
            height=1100,
        )
        return figure

    def render_comparison(
        self,
        report: StrategyComparisonReportDto,
        equities: dict[str, pd.Series],
    ) -> go.Figure:
        """權益曲線疊圖 ＋ 相關性熱力圖。

        兩格放在一起是刻意的：上面看「誰賺得多」，下面看「它們是不是同一個賭注」。
        只看上面那格會得到「分散到三個策略」的錯覺。
        """
        figure = make_subplots(
            rows=2,
            cols=1,
            vertical_spacing=0.12,
            row_heights=[0.62, 0.38],
            subplot_titles=(
                f"權益曲線（{report.period_label}，同一段資料、同一組成本）",
                "策略之間的相關性（只算兩邊都有部位的那些根）",
            ),
        )
        for name, equity in equities.items():
            figure.add_trace(
                go.Scatter(
                    x=equity.index,
                    y=equity.to_numpy(),
                    mode="lines",
                    name=name,
                    line={"dash": "dash"} if name == "buy_and_hold" else None,
                ),
                row=1,
                col=1,
            )

        names = list(report.correlation.index)
        figure.add_trace(
            go.Heatmap(
                z=report.correlation.to_numpy(),
                x=names,
                y=names,
                zmin=-1.0,
                zmax=1.0,
                colorbar={"title": "相關係數"},
            ),
            row=2,
            col=1,
        )
        figure.update_layout(title="多策略比較", height=1000)
        return figure
