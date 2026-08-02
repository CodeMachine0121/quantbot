# quantbot/infrastructure/charting/plotly_relative_strength_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.rsi import RSI


class PlotlyRelativeStrengthChartRenderer:
    """上格 K 線、下格 RSI，共用同一條 x 軸。

    動能指標的單位跟價格不一樣，不能疊在 K 線上，所以要另外開子圖。
    三條水平線的位置與顏色是類別常數：70 / 30 是慣例閾值，50 是中線。
    """

    LEVELS: ClassVar[tuple[tuple[int, str, str], ...]] = (
        (70, "dash", "#c0392b"),
        (50, "dot", "#95a5a6"),
        (30, "dash", "#27ae60"),
    )

    def __init__(self, *, period: int = 14) -> None:
        self._indicator = RSI(period)

    def render(self, series: CandleSeries) -> go.Figure:
        line = self._indicator.compute(series)
        candles = series.frame

        figure = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.7, 0.3],
            subplot_titles=(
                series.instrument.storage_key,
                f"RSI({self._indicator.period})",
            ),
        )
        figure.add_trace(
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name=series.instrument.symbol,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(x=line.index, y=line, name=str(line.name), line={"width": 1.4}),
            row=2,
            col=1,
        )
        for level, dash, color in self.LEVELS:
            figure.add_hline(
                y=level, line_dash=dash, line_color=color, line_width=1, row=2, col=1
            )

        figure.update_yaxes(title_text="價格（USDT）", row=1, col=1)
        figure.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
        figure.update_xaxes(title_text="時間（UTC）", row=2, col=1)
        figure.update_layout(
            height=760,
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
            showlegend=False,
        )
        return figure
