# quantbot/infrastructure/charting/plotly_smoothing_comparison_renderer.py
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.ema import EMA
from quantbot.domain.indicators.sma import SMA
from quantbot.domain.values.time_range import TimeRange


class PlotlySmoothingComparisonRenderer:
    """同一段收盤價上 SMA 與 EMA 的對照：兩條線、急跌區間、擺動次數。

    兩條線在**完整資料**上算完再切片，NEVER 先切片再算——切出來的那一小段
    前面沒有暖機資料，EMA 的起始值會失真，這正是今天講的種子問題。
    """

    SMA_LINE: ClassVar[str] = "#1f77b4"
    EMA_LINE: ClassVar[str] = "#ff7f0e"
    DIFFERENCE_BAR: ClassVar[str] = "#9467bd"

    def __init__(self, *, period: int = 20) -> None:
        self.period = period
        self._sma = SMA(period)
        self._ema = EMA(period)

    def steepest_drop(
        self, series: CandleSeries, *, window_bars: int = 6, span_bars: int = 120
    ) -> CandleSeries:
        """樣本裡跌得最急的一段：以 window_bars 根報酬最低的位置為中心。"""
        candles = series.frame
        centre = pd.Timestamp(candles["close"].pct_change(window_bars).idxmin())
        step = series.instrument.timeframe.step
        return series.restricted_to(
            TimeRange(centre - step * span_bars, centre + step * span_bars)
        )

    def direction_flips(self, series: CandleSeries) -> dict[str, int]:
        """兩條線各自換方向幾次。次數越多，代表線越常來回擺動。"""
        return {
            "sma": self._count_flips(self._sma.compute(series)),
            "ema": self._count_flips(self._ema.compute(series)),
        }

    def render(self, series: CandleSeries, segment: CandleSeries) -> go.Figure:
        sma_line = self._sma.compute(series).loc[segment.open_times]
        ema_line = self._ema.compute(series).loc[segment.open_times]
        candles = segment.frame

        figure = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.04,
            subplot_titles=(
                f"{series.instrument.storage_key}："
                f"SMA({self.period}) vs EMA({self.period})",
                "SMA − EMA（正值代表 EMA 已經先往下）",
            ),
        )
        figure.add_trace(
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name="K 線",
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            ),
            row=1,
            col=1,
        )
        for line, color in ((sma_line, self.SMA_LINE), (ema_line, self.EMA_LINE)):
            figure.add_trace(
                go.Scatter(
                    x=line.index,
                    y=line,
                    name=str(line.name),
                    line={"color": color, "width": 2},
                ),
                row=1,
                col=1,
            )
        figure.add_trace(
            go.Bar(
                x=candles.index,
                y=sma_line - ema_line,
                name="SMA − EMA",
                marker_color=self.DIFFERENCE_BAR,
            ),
            row=2,
            col=1,
        )
        figure.add_hline(y=0, line_width=1, line_color="#888", row=2, col=1)
        figure.update_layout(
            height=760,
            xaxis_rangeslider_visible=False,
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.04},
            margin={"l": 60, "r": 30, "t": 90, "b": 40},
        )
        figure.update_yaxes(title_text="價格（USDT）", row=1, col=1)
        figure.update_yaxes(title_text="價差（USDT）", row=2, col=1)
        figure.update_xaxes(title_text="時間（UTC）", row=2, col=1)
        return figure

    @staticmethod
    def _count_flips(line: pd.Series) -> int:
        slope = np.diff(line.dropna().to_numpy())
        return int(np.sum(np.sign(slope[1:]) != np.sign(slope[:-1])))
