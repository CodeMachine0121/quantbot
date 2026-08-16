# quantbot/infrastructure/charting/plotly_cost_comparison_renderer.py
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go

from quantbot.domain.dto.backtest_report import BacktestReportDto


class PlotlyCostComparisonRenderer:
    """加成本前後的權益曲線疊在同一張圖上。

    疊圖而不是並排兩張：要看的是兩條線**什麼時候開始分開、分得多快**，而那是
    同一個時間軸上的距離。分成兩張圖就得靠眼睛在兩邊來回對，而兩張圖的 y 軸範圍
    多半不一樣，看起來的斜率會騙人。

    基準策略（BuyAndHold）也畫進來，因為「策略賠錢」與「市場在跌」是兩件事，
    而分辨它們唯一的方法是把基準放在同一張圖上。
    """

    def render(
        self,
        report: BacktestReportDto,
        *,
        baseline: BacktestReportDto | None = None,
    ) -> go.Figure:
        figure = go.Figure()
        self._add(figure, report.gross_equity, "未扣成本", dash="dot")
        self._add(figure, report.equity, f"扣成本（{report.costs.describe()}）")
        if baseline is not None:
            self._add(figure, baseline.equity, "BuyAndHold 基準", dash="dash")

        figure.update_layout(
            title=(
                f"{report.strategy_name}：成本吃掉了多少"
                f"（{report.trade_count} 筆交易，換手 {report.turnover:.0f} 倍，"
                f"試驗次數 {report.trial_count}）"
            ),
            xaxis_title="時間（UTC）",
            yaxis_title="權益",
            hovermode="x unified",
        )
        return figure

    def render_sensitivity(
        self,
        round_trip_rates: Sequence[float],
        total_returns: Sequence[float],
    ) -> go.Figure:
        """來回成本率對總報酬的曲線，並標出零報酬那條水平線。

        零那條線是這張圖的重點：曲線跟它的交點就是這個策略還撐得住的成本上限。
        """
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=[rate * 100.0 for rate in round_trip_rates],
                y=[value * 100.0 for value in total_returns],
                mode="lines+markers",
                name="總報酬",
            )
        )
        figure.add_hline(y=0.0, line_dash="dash")
        figure.update_layout(
            title="成本敏感度：來回成本率對總報酬",
            xaxis_title="來回成本率（%）",
            yaxis_title="總報酬（%）",
        )
        return figure

    @staticmethod
    def _add(
        figure: go.Figure, equity: pd.Series, name: str, *, dash: str | None = None
    ) -> None:
        figure.add_trace(
            go.Scatter(
                x=equity.index,
                y=equity.to_numpy(),
                mode="lines",
                name=name,
                line={"dash": dash} if dash is not None else None,
            )
        )
