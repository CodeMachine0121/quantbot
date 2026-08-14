# quantbot/infrastructure/charting/plotly_search_distribution_renderer.py
from __future__ import annotations

import plotly.graph_objects as go

from quantbot.domain.dto.search_report import SearchReportDto


class PlotlySearchDistributionRenderer:
    """真實資料與打亂順序的假資料，兩次搜尋的樣本內夏普分布疊在同一張圖。

    這張圖本身就是論證，所以它要能被單獨看懂：兩片分布如果重疊，那就表示真實資料
    上「找到」的那些漂亮結果，在完全沒有訊號的資料上也找得到——於是搜尋本身沒有
    篩掉任何東西。

    圖上刻意不用顏色表達好壞（深淺色主題下顏色的意義會變），兩片分布靠圖例區分，
    而那條垂直線標的是「純靠運氣的期望上限」。
    """

    def render(self, actual: SearchReportDto, shuffled: SearchReportDto) -> go.Figure:
        figure = go.Figure()
        for report in (actual, shuffled):
            figure.add_trace(
                go.Histogram(
                    x=list(report.in_sample_sharpes),
                    name=f"{report.label}（{report.trial_count} 種組合）",
                    opacity=0.6,
                    nbinsx=30,
                )
            )
        figure.add_vline(
            x=actual.expected_maximum_sharpe,
            line_dash="dash",
            annotation_text="純靠運氣的期望上限",
        )
        figure.update_layout(
            barmode="overlay",
            title=(
                "樣本內夏普的分布：真實資料 vs 打亂順序的假資料"
                f"（各 {actual.trial_count} 種組合）"
            ),
            xaxis_title="樣本內夏普比率",
            yaxis_title="組合數",
        )
        return figure

    def render_in_versus_out(self, report: SearchReportDto) -> go.Figure:
        """樣本內夏普對樣本外夏普的散布圖。

        有真的訊號的話，點會沿著左下到右上的方向排；只有雜訊的話，點會是一團雲，
        而那團雲的形狀比任何單一個排名都說得清楚。
        """
        pairs = [
            (trial.in_sample_sharpe, trial.out_of_sample_sharpe, trial.strategy_name)
            for trial in report.trials
            if trial.in_sample_sharpe is not None
            and trial.out_of_sample_sharpe is not None
        ]
        figure = go.Figure(
            go.Scatter(
                x=[pair[0] for pair in pairs],
                y=[pair[1] for pair in pairs],
                text=[pair[2] for pair in pairs],
                mode="markers",
                name=report.label,
            )
        )
        figure.add_hline(y=0.0, line_dash="dot")
        figure.add_vline(x=0.0, line_dash="dot")
        figure.update_layout(
            title=f"{report.label}：樣本內對樣本外（{len(pairs)} 種組合）",
            xaxis_title="樣本內夏普比率",
            yaxis_title="樣本外夏普比率",
        )
        return figure
