# quantbot/infrastructure/charting/plotly_activity_heatmap_renderer.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from quantbot.domain.values.activity_measure import ActivityMeasure
from quantbot.domain.values.market_view import MarketView


class PlotlyActivityHeatmapRenderer:
    """星期 × 鐘點的活躍度熱力圖。

    用熱力圖而不是折線圖，因為要看的是**兩個週期疊在一起**的結構：一天之內的
    時段節奏，以及一週之內的星期節奏。折線圖只能表達一個週期，另一個會被攤平。

    格子裡放的是「該時段的平均值除以整體平均」，也就是倍數。用倍數而不是原始值，
    圖的色階才不會被幣價或交易對的量級綁住，換一個交易對還是同一張圖看得懂。
    """

    WEEKDAY_LABELS = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")

    def __init__(self, measure: ActivityMeasure = ActivityMeasure.TRADE_COUNT) -> None:
        self._measure = measure

    def render(self, view: MarketView) -> go.Figure:
        grid = self.multiples(view)

        figure = go.Figure(
            go.Heatmap(
                z=grid.to_numpy(),
                x=[f"{hour:02d}" for hour in grid.columns],
                y=[self.WEEKDAY_LABELS[weekday] for weekday in grid.index],
                colorscale="RdBu_r",
                zmid=1.0,
                colorbar={"title": "相對於整體平均"},
                hovertemplate="%{y} %{x}:00（UTC）<br>%{z:.2f} 倍<extra></extra>",
            )
        )
        figure.update_layout(
            title=(
                f"{view.instrument.storage_key}：{self._measure} 的時段節奏"
                f"（{len(view.candles):,} 根 K 線）"
            ),
            xaxis_title="UTC 鐘點",
            yaxis_title="星期",
            height=460,
        )
        return figure

    def multiples(self, view: MarketView) -> pd.DataFrame:
        """每個（星期, 鐘點）格子的平均值 ÷ 整體平均。

        這張表本身就是結論，所以它是一個可以被單獨取用、單獨測試的方法，
        而不是埋在畫圖流程裡的中間變數。
        """
        values = self._measure.of(view.candles.frame)
        times = pd.DatetimeIndex(values.index)
        tabular = pd.DataFrame(
            {
                "weekday": times.dayofweek,
                "hour": times.hour,
                "value": values.to_numpy(),
            }
        )
        grid = tabular.pivot_table(
            index="weekday", columns="hour", values="value", aggfunc="mean"
        )
        return grid / float(values.mean())
