# quantbot/domain/dto/strategy_comparison_report.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.domain.dto.performance_summary import PerformanceSummaryDto


@dataclass(frozen=True)
class StrategyComparisonReportDto:
    """幾個策略並排比較的結果。

    公平比較的四個條件都由這份 DTO 的形狀保證，而不是靠使用者記得：

    1. **同一段資料。** 所有摘要的 bar_count 相同（建構時檢查）。
    2. **同一組成本假設。** 由呼叫端傳同一份 BacktestSpecification 保證。
    3. **同樣標注試驗次數。** 每一列都有 trial_count，那個欄位沒有預設值。
    4. **有基準。** baseline 是必填的，所以一份沒有基準的比較根本建不出來。

    第四點是這份 DTO 最重要的欄位。少了基準，「總報酬 −2.45%」看起來像個壞結果；
    放上基準（同期間 BuyAndHold −35.20%）之後它是另一件事。而反過來也成立：
    一個 +40% 的策略在一個 +80% 的市場裡是災難。
    """

    period_label: str
    baseline: PerformanceSummaryDto
    summaries: tuple[PerformanceSummaryDto, ...]
    correlation: pd.DataFrame

    def __post_init__(self) -> None:
        if not self.summaries:
            raise ValueError("至少要有一個策略")
        bar_counts = {summary.bar_count for summary in self.summaries}
        bar_counts.add(self.baseline.bar_count)
        if len(bar_counts) != 1:
            raise ValueError(
                f"並排比較必須跑在同一段資料上，實得根數 {sorted(bar_counts)}"
            )

    def ranked_by_sharpe(self) -> tuple[PerformanceSummaryDto, ...]:
        """依夏普排名。**排第一不等於最該上線的那一個**，見 Day 22。"""
        return tuple(
            sorted(
                self.summaries,
                key=lambda summary: (
                    summary.sharpe_ratio if summary.sharpe_ratio is not None else -1e9
                ),
                reverse=True,
            )
        )

    def beating_the_baseline(self) -> tuple[PerformanceSummaryDto, ...]:
        """贏過基準的那些。贏不過的策略只是在製造手續費。"""
        return tuple(
            summary
            for summary in self.summaries
            if summary.total_return > self.baseline.total_return
        )

    @property
    def most_correlated_pair(self) -> tuple[str, str, float] | None:
        """相關性最高的一對。兩個高度相關的策略同時上線等於加大同一個賭注。"""
        highest: tuple[str, str, float] | None = None
        names = list(self.correlation.index)
        for row, first in enumerate(names):
            for second in names[row + 1 :]:
                value = self.correlation.loc[first, second]
                if pd.isna(value):
                    continue
                if highest is None or float(value) > highest[2]:
                    highest = (first, second, float(value))
        return highest
