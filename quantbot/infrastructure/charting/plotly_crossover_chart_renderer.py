# quantbot/infrastructure/charting/plotly_crossover_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import pandas as pd
import plotly.graph_objects as go

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.crossover_signals import CrossoverSignals
from quantbot.domain.indicators.sma import SMA


class PlotlyCrossoverChartRenderer:
    """K 線疊兩條 SMA，並把交叉標在快線上。

    圖表在 infrastructure：domain 不知道 plotly 存在，所以換成 matplotlib
    或前端畫圖時，指標與訊號一行都不用改。配色是類別常數，整個系列共用一組。
    """

    CANDLE_UP: ClassVar[str] = "#26a69a"
    CANDLE_DOWN: ClassVar[str] = "#ef5350"
    FAST_LINE: ClassVar[str] = "#f4a261"
    SLOW_LINE: ClassVar[str] = "#4c6ef5"
    MARKERS: ClassVar[tuple[tuple[str, str, str, str], ...]] = (
        ("golden", "黃金交叉", "triangle-up", "#2f9e44"),
        ("death", "死亡交叉", "triangle-down", "#c92a2a"),
    )

    def __init__(self, *, fast_period: int = 20, slow_period: int = 60) -> None:
        self._fast = SMA(fast_period)
        self._slow = SMA(slow_period)

    def render(self, series: CandleSeries) -> go.Figure:
        fast = self._fast.compute(series)
        slow = self._slow.compute(series)
        crosses = CrossoverSignals(fast, slow)

        figure = go.Figure()
        figure.add_trace(self._candles(series))
        figure.add_trace(self._line(fast, self._fast.period, self.FAST_LINE))
        figure.add_trace(self._line(slow, self._slow.period, self.SLOW_LINE))
        for attribute, label, symbol, color in self.MARKERS:
            figure.add_trace(
                self._markers(fast, getattr(crosses, attribute), label, symbol, color)
            )
        figure.update_layout(**self._layout(series))
        return figure

    def _candles(self, series: CandleSeries) -> go.Candlestick:
        candles = series.frame
        return go.Candlestick(
            x=candles.index,
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name=series.instrument.storage_key,
            increasing_line_color=self.CANDLE_UP,
            decreasing_line_color=self.CANDLE_DOWN,
        )

    @staticmethod
    def _line(values: pd.Series, period: int, color: str) -> go.Scatter:
        return go.Scatter(
            x=values.index,
            y=values,
            name=f"SMA({period})",
            mode="lines",
            line={"width": 1.6, "color": color},
        )

    @staticmethod
    def _markers(
        fast: pd.Series, hit: pd.Series, label: str, symbol: str, color: str
    ) -> go.Scatter:
        # 標記畫在快線上：交叉是兩條線的事件，位置才對得起來
        return go.Scatter(
            x=fast.index[hit],
            y=fast[hit],
            name=label,
            mode="markers",
            marker={
                "symbol": symbol,
                "size": 12,
                "color": color,
                "line": {"width": 1, "color": "white"},
            },
        )

    def _layout(self, series: CandleSeries) -> dict[str, object]:
        instrument = series.instrument
        return {
            "title": (
                f"{instrument.symbol} {instrument.market} {instrument.timeframe}："
                f"SMA({self._fast.period}) 與 SMA({self._slow.period}) 交叉"
            ),
            "xaxis_title": "時間（UTC）",
            "yaxis_title": "價格（USDT）",
            "xaxis_rangeslider_visible": False,
            "height": 620,
            "hovermode": "x unified",
        }
