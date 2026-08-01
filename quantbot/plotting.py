import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_ohlcv(frame: pd.DataFrame, title: str) -> go.Figure:

    """畫出 K 線與成交量的雙層圖。

    Args:
        frame: 需要 UTC 的 DatetimeIndex 與 open/high/low/close/volume 欄位。
        title: 圖表標題，MUST 標明交易對與市場類型。
    """

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
        subplot_titles=(
            "價格 open / high / low / close (USDT)",
            "成交量 volume (BTC)",
        ),
    )

    figure.add_trace(
        go.Candlestick(
            x=frame.index,
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    figure.add_trace(
        go.Bar(
            x=frame.index,
            y=frame["volume"],
            name="volume",
            marker_color="#78909c",
        ),
        row=2,
        col=1,
    )

    figure.update_layout(
        title=title,
        height=720,
        showlegend=False,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
    )
    figure.update_xaxes(title_text="時間（UTC）", row=2, col=1)

    return figure
