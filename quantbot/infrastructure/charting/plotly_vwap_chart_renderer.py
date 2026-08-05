# quantbot/infrastructure/charting/plotly_vwap_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.features.volume_weighted_average_price import VWAP
from quantbot.domain.features.vwap_deviation import VWAPDeviation
from quantbot.domain.values.market_view import MarketView


class PlotlyVWAPChartRenderer:
    """上格 K 線 ＋ VWAP ＋ 標準差通道，下格偏離度。

    通道用同一張圖疊上去而不是分兩張：要看的是「價格現在在通道的哪裡」，
    那是一個相對位置，拆成兩張圖就得靠眼睛在兩邊來回對時間軸。

    下格的偏離度是無單位的，所以它有固定的水平線可以標（±1、±2）。上格的通道
    寬度會隨行情變化，下格的門檻不會——這正是標準化的用處。
    """

    BAND_MULTIPLIERS: ClassVar[tuple[float, ...]] = (1.0, 2.0)
    BAND_COLORS: ClassVar[tuple[str, ...]] = ("#7f8c8d", "#c0392b")

    def __init__(self, feature: VWAP) -> None:
        self._feature = feature
        self._deviation = VWAPDeviation(feature)

    def render(self, view: MarketView) -> go.Figure:
        candles = view.candles.frame
        line = self._feature.compute(view)
        spread = self._feature.standard_deviation(view)
        deviation = self._deviation.compute(view)

        figure = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.72, 0.28],
            subplot_titles=(
                f"{view.instrument.storage_key}：{self._feature.name}"
                f"（{self._feature.price_source} 價）",
                "偏離度（加權標準差的倍數）",
            ),
        )
        figure.add_trace(
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name=view.instrument.symbol,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=line.index,
                y=line,
                name=str(line.name),
                line={"width": 1.8, "color": "#2c3e50"},
            ),
            row=1,
            col=1,
        )
        for multiplier, color in zip(
            self.BAND_MULTIPLIERS, self.BAND_COLORS, strict=True
        ):
            for sign in (1, -1):
                figure.add_trace(
                    go.Scatter(
                        x=line.index,
                        y=line + sign * multiplier * spread,
                        name=f"{sign * multiplier:+.0f} 標準差",
                        line={"width": 0.9, "color": color, "dash": "dash"},
                        showlegend=sign > 0,
                    ),
                    row=1,
                    col=1,
                )

        figure.add_trace(
            go.Scatter(
                x=deviation.index,
                y=deviation,
                name=str(deviation.name),
                line={"width": 1.1, "color": "#2980b9"},
            ),
            row=2,
            col=1,
        )
        for level in (2.0, 0.0, -2.0):
            figure.add_hline(
                y=level,
                line_dash="dot" if level else "solid",
                line_color="#95a5a6",
                line_width=1,
                row=2,
                col=1,
            )

        figure.update_yaxes(title_text="價格（USDT）", row=1, col=1)
        figure.update_yaxes(title_text="標準差倍數", row=2, col=1)
        figure.update_xaxes(title_text="時間（UTC）", row=2, col=1)
        figure.update_layout(
            height=820, xaxis_rangeslider_visible=False, hovermode="x unified"
        )
        return figure
