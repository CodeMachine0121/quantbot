# quantbot/infrastructure/charting/plotly_breakout_chart_renderer.py
from __future__ import annotations

from typing import ClassVar

import plotly.graph_objects as go

from quantbot.domain.features.breakout import Breakout
from quantbot.domain.services.breakout_labelling_service import (
    BreakoutLabellingService,
)
from quantbot.domain.values.breakout_label import BreakoutLabel
from quantbot.domain.values.market_view import MarketView


class PlotlyBreakoutChartRenderer:
    """K 線 ＋ 前高線 ＋ 把突破依標籤標成兩種顏色的標記。

    這張圖的用途不是找訊號，是**用眼睛確認標記邏輯正確**。統計數字沒辦法告訴我們
    「突破」這個判斷有沒有寫錯——一個把 shift 寫掉的版本會產生 0 個事件（統計上
    看起來像「這段行情很平靜」），一個把方向寫反的版本會把每個低點標成突破。
    這兩種錯誤在圖上一秒就看得出來。

    所以它刻意把兩種標籤畫成不同顏色：守住的往上三角、被打回來的往下三角。
    肉眼掃過去，被打回來的那些應該落在圖形的相對高點附近。
    """

    HELD_COLOR: ClassVar[str] = "#27ae60"
    FAILED_COLOR: ClassVar[str] = "#c0392b"

    def __init__(
        self, *, breakout: Breakout, labelling: BreakoutLabellingService
    ) -> None:
        self._breakout = breakout
        self._labelling = labelling

    def render(self, view: MarketView) -> go.Figure:
        candles = view.candles.frame
        prior_level = self._breakout.prior_level(view)
        labels = self._labelling.label(view, self._breakout)
        label_column = labels[BreakoutLabellingService.LABEL_COLUMN]

        figure = go.Figure()
        figure.add_trace(
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name=view.instrument.symbol,
            )
        )
        # 前高線用階梯狀（hv）而不是直線：它在被突破之前是一個常數，
        # 用斜線連起來會讓人以為那個門檻在中間慢慢移動
        figure.add_trace(
            go.Scatter(
                x=prior_level.index,
                y=prior_level,
                name=f"前 {self._breakout.window} 根極值",
                line={"width": 1.0, "color": "#8e44ad", "shape": "hv"},
            )
        )

        for label, color, symbol in (
            (BreakoutLabel.HELD, self.HELD_COLOR, "triangle-up"),
            (BreakoutLabel.FAILED, self.FAILED_COLOR, "triangle-down"),
        ):
            selected = labels.loc[label_column == label.value]
            figure.add_trace(
                go.Scatter(
                    x=selected.index,
                    y=candles.loc[selected.index, self._breakout.side.column],
                    mode="markers",
                    name=f"{label.value}（{len(selected)}）",
                    marker={"size": 9, "color": color, "symbol": symbol},
                )
            )

        figure.update_layout(
            title=(
                f"{view.instrument.storage_key}：{self._breakout.name}"
                f"（觀察窗 {self._labelling.horizon} 根）"
            ),
            yaxis_title="價格（USDT）",
            xaxis_title="時間（UTC）",
            height=720,
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
        )
        return figure
