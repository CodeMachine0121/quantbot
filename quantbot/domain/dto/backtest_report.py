# quantbot/domain/dto/backtest_report.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.values.cost_model import CostModel


@dataclass(frozen=True)
class BacktestReportDto:
    """一次回測的結果。

    它刻意**只放原始結果**，不放績效指標。夏普、最大回撤、勝率都是從權益曲線與
    交易明細算出來的，而算它們的地方是 PerformanceMetricsService（Day 21 與 22）。
    分開的理由是這份 DTO 會被存下來、被比較、被畫圖，而每次多一個指標就改一次
    形狀的東西沒辦法當共同基準。

    trial_count 沒有預設值，所以**建不出一份沒有標注試驗次數的報告**。這條從今天
    起適用到系列結束：一個「試了 500 個組合挑出來的最佳結果」與一個「只跑了一次的
    結果」，數字看起來一樣但可信度差好幾個數量級。Day 21 會說明差多少。
    """

    strategy_name: str
    bar_count: int
    trade_count: int
    trial_count: int
    initial_capital: float
    costs: CostModel
    equity: pd.Series
    gross_equity: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    turnover: float
    cost_paid: float

    @property
    def final_equity(self) -> float:
        if self.equity.empty:
            return self.initial_capital
        return float(self.equity.iloc[-1])

    @property
    def total_return(self) -> float:
        """扣掉成本之後的總報酬率。"""
        return self.final_equity / self.initial_capital - 1.0

    @property
    def gross_total_return(self) -> float:
        """沒扣成本的總報酬率。它是理想回測的那個數字。"""
        if self.gross_equity.empty:
            return 0.0
        return float(self.gross_equity.iloc[-1]) / self.initial_capital - 1.0

    @property
    def cost_share_of_gross_profit(self) -> float | None:
        """成本吃掉了毛利的幾成。

        毛利是負的或零時回 None 而不是一個數字：那時候「成本佔毛利」沒有意義，
        而硬算出來的百分比會被誤讀成「成本不高」。
        """
        gross_profit = float(self.gross_equity.iloc[-1]) - self.initial_capital
        if gross_profit <= 0.0:
            return None
        return self.cost_paid / gross_profit

    @property
    def exposure(self) -> float:
        """有部位的根數佔總根數的比例。比較兩個策略的報酬之前一定要先看它。

        它數的是交易明細的持有根數，NEVER 數「報酬不為零的根數」——出場那一根的
        報酬不為零（付了手續費）但部位已經是空的，照後者算會把曝險算高。
        """
        if self.bar_count == 0 or self.trades.empty:
            return 0.0
        return float(self.trades["bars_held"].sum()) / self.bar_count
