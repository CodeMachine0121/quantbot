# quantbot/infrastructure/charting/plotly_volume_profile_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.volume_profile import VolumeProfile


class PlotlyVolumeProfileChartRenderer:
    """左邊 K 線，右邊橫向的成交量分布，共用同一條價格軸。

    橫向長條圖是這個指標的傳統畫法，而它不只是美觀：**分布的 y 軸就是 K 線的 y 軸**，
    所以「POC 在哪個價位」可以直接用眼睛連到左邊的 K 線上。畫成一般的直立長條圖
    （x 軸是價格）就得在腦中轉九十度，而那一步很容易看錯。

    兩張 profile 疊在同一格：精算的實心、近似的外框。要看的是它們的**形狀差異**，
    分成兩格就得靠眼睛在兩邊來回對價位。
    """

    EXACT_COLOR: ClassVar[str] = "#2980b9"
    APPROXIMATE_COLOR: ClassVar[str] = "#e67e22"

    def render(
        self,
        candles: CandleSeries,
        exact: VolumeProfile,
        approximate: VolumeProfile,
    ) -> go.Figure:
        figure = make_subplots(
            rows=1,
            cols=2,
            shared_yaxes=True,
            column_widths=[0.72, 0.28],
            horizontal_spacing=0.02,
            subplot_titles=(
                candles.instrument.storage_key,
                "價格軸上的成交量分布",
            ),
        )
        frame = candles.frame
        figure.add_trace(
            go.Candlestick(
                x=frame.index,
                open=frame["open"],
                high=frame["high"],
                low=frame["low"],
                close=frame["close"],
                name=candles.instrument.symbol,
            ),
            row=1,
            col=1,
        )

        for profile, color, name, opacity in (
            (exact, self.EXACT_COLOR, "逐筆精算", 0.85),
            (approximate, self.APPROXIMATE_COLOR, "K 線近似", 0.45),
        ):
            figure.add_trace(
                go.Bar(
                    x=profile.volume_by_price.to_numpy(),
                    y=profile.volume_by_price.index.to_numpy(),
                    orientation="h",
                    name=name,
                    marker={"color": color},
                    opacity=opacity,
                ),
                row=1,
                col=2,
            )

        # 三條水平線畫在 K 線那一格：POC 與價值區間上下緣才是要拿去用的價位
        levels = exact.key_levels()
        for key, dash in (
            ("point_of_control", "solid"),
            ("value_area_high", "dash"),
            ("value_area_low", "dash"),
        ):
            figure.add_hline(
                y=levels[key],
                line_dash=dash,
                line_color=self.EXACT_COLOR,
                line_width=1.2,
                annotation_text=f"{key} {levels[key]:,.0f}",
                annotation_position="right",
                row=1,
                col=1,
            )

        figure.update_yaxes(title_text="價格（USDT）", row=1, col=1)
        figure.update_xaxes(title_text="時間（UTC）", row=1, col=1)
        figure.update_xaxes(title_text="成交量（BTC）", row=1, col=2)
        figure.update_layout(
            height=760,
            xaxis_rangeslider_visible=False,
            barmode="overlay",
            bargap=0.05,
        )
        return figure
