# quantbot/infrastructure/charting/plotly_imbalance_power_chart_renderer.py
from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.dto.predictive_power_report import PredictivePowerReportDto
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.features.order_book_imbalance import OrderBookImbalance


class PlotlyImbalancePowerChartRenderer:
    """上格 OBI 與中間價疊圖，下格分組報酬長條圖。

    兩張圖回答的是兩個不同的問題，所以要並排在同一份輸出裡：上格回答「這個特徵
    長什麼樣子」（會不會一直貼在極值、有沒有明顯的躁動），下格回答「它有沒有用」。
    只看上格會誤以為一個劇烈擺動的序列一定有資訊。

    OBI 與價格的量級差了六個數量級，所以用左右雙軸而不是硬疊在同一軸上。
    """

    def __init__(self, feature: OrderBookImbalance) -> None:
        self._feature = feature

    def render(
        self, depth: DepthSeries, reports: Sequence[PredictivePowerReportDto]
    ) -> go.Figure:
        ratio = self._feature.ratio(depth.frame)
        mid = depth.mid_price()

        figure = make_subplots(
            rows=2,
            cols=1,
            vertical_spacing=0.12,
            row_heights=[0.62, 0.38],
            specs=[[{"secondary_y": True}], [{}]],
            subplot_titles=(
                f"{depth.listing.storage_key}：{self._feature.name} 與中間價",
                "按 OBI 分組的未來報酬（每組樣本數相同）",
            ),
        )
        figure.add_trace(
            go.Scatter(
                x=mid.index,
                y=mid,
                name="中間價",
                line={"width": 1.2, "color": "#34495e"},
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=ratio.index,
                y=ratio,
                name=str(ratio.name),
                line={"width": 1.0, "color": "#2980b9"},
                opacity=0.75,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
        figure.add_hline(
            y=0.0, line_dash="dot", line_color="#95a5a6", row=1, col=1, secondary_y=True
        )

        for report in reports:
            figure.add_trace(
                go.Bar(
                    x=[
                        f"第 {index + 1} 組"
                        for index in range(len(report.bucket_mean_returns))
                    ],
                    # 報酬用基點（萬分之一）表示，不然刻度上全是 0.0000
                    y=[value * 10_000 for value in report.bucket_mean_returns],
                    name=f"往後 {report.horizon} 格",
                ),
                row=2,
                col=1,
            )

        figure.update_yaxes(
            title_text="中間價（USDT）", row=1, col=1, secondary_y=False
        )
        figure.update_yaxes(
            title_text="OBI", range=[-1.05, 1.05], row=1, col=1, secondary_y=True
        )
        figure.update_yaxes(title_text="平均未來報酬（bp）", row=2, col=1)
        figure.update_xaxes(title_text="時間（UTC）", row=1, col=1)
        figure.update_xaxes(title_text="OBI 由低到高分組", row=2, col=1)
        figure.update_layout(height=820, hovermode="x unified", barmode="group")
        return figure
