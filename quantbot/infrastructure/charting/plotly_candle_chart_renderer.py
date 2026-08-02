# quantbot/infrastructure/charting/plotly_candle_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quantbot.domain.entities.candle_series import CandleSeries


class PlotlyCandleChartRenderer:
    """K 線與成交量的雙層圖。OHLCV 五個欄位全部畫出來，不要只畫價格。

    它住在 infrastructure，因為它認識 plotly。domain 那邊不知道有畫圖這件事，
    所以之後換成 matplotlib 或前端畫圖，K 線的資料結構一行都不用改。
    """

    CANDLE_UP: ClassVar[str] = "#26a69a"
    CANDLE_DOWN: ClassVar[str] = "#ef5350"
    VOLUME_BAR: ClassVar[str] = "#78909c"

    def render(self, series: CandleSeries) -> go.Figure:
        candles = series.frame
        instrument = series.instrument

        figure = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.04,
            subplot_titles=(
                "價格 open / high / low / close (USDT)",
                f"成交量 volume ({instrument.symbol.split('/')[0]})",
            ),
        )
        figure.add_trace(
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name="OHLC",
                increasing_line_color=self.CANDLE_UP,
                decreasing_line_color=self.CANDLE_DOWN,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Bar(
                x=candles.index,
                y=candles["volume"],
                name="volume",
                marker_color=self.VOLUME_BAR,
            ),
            row=2,
            col=1,
        )
        figure.update_layout(
            # 標題從 instrument 長出來，不手寫字串：市場類型與粒度一定會標到
            title=(
                f"{instrument.symbol} {instrument.market} "
                f"{instrument.timeframe}（data.binance.vision）"
            ),
            height=720,
            showlegend=False,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
        )
        figure.update_xaxes(title_text="時間（UTC）", row=2, col=1)
        return figure
