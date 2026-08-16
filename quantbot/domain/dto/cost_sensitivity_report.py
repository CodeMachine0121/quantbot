# quantbot/domain/dto/cost_sensitivity_report.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostSensitivityRowDto:
    """一個成本假設下的結果。"""

    taker_fee_rate: float
    slippage_rate: float
    total_return: float
    cost_paid: float
    cost_share_of_gross_profit: float | None

    @property
    def round_trip_rate(self) -> float:
        return 2.0 * (self.taker_fee_rate + self.slippage_rate)


@dataclass(frozen=True)
class CostSensitivityReportDto:
    """同一個策略在幾種成本假設下的結果，以及它在哪一點由賺轉賠。

    這份報告要回答的問題不是「這個策略賺多少」，是「它對成本有多敏感」。兩個
    總報酬一樣的策略，一個換手 464 倍、一個換手 2 倍，前者的績效幾乎完全由費率
    決定，而那件事在單一個數字上看不出來。

    break_even_round_trip_rate 是線性內插出來的，不是網格上的某一點。它會是
    None——當策略在最低的成本假設下就已經賠錢（那時候「由賺轉賠的位置」不存在），
    或者在最高的成本假設下還在賺（那時候只知道它在網格之外）。
    """

    strategy_name: str
    trade_count: int
    turnover: float
    gross_total_return: float
    rows: tuple[CostSensitivityRowDto, ...]
    break_even_round_trip_rate: float | None

    @property
    def cost_per_trade_rate(self) -> float:
        """平均一筆交易換手幾倍。

        換手除以交易筆數，正常應該接近 2（進場一次、出場一次）。明顯小於 2 表示
        有很多筆在回測結束時還開著，或者部位在中途沒有完全平掉。
        """
        if self.trade_count == 0:
            return 0.0
        return self.turnover / self.trade_count
