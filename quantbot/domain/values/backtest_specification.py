# quantbot/domain/values/backtest_specification.py
from __future__ import annotations

from dataclasses import dataclass, field

from quantbot.domain.values.cost_model import CostModel


@dataclass(frozen=True)
class BacktestSpecification:
    """一次回測的設定：起始資金與成本模型。

    起始資金在這一階段只影響權益曲線的刻度，不影響報酬率——因為部位是滿倉進出的
    比例，沒有「買得起幾股」的問題。它還是要有，因為 Day 24 加上部位大小之後，
    「一次下多少錢」會跟總資金綁在一起，而那時候刻度就有意義了。

    成本模型是必填的（有預設值但沒有被藏起來），而且預設就是真實的 taker 費率。
    要跑理想回測必須明確寫 CostModel.frictionless()——這個順序是刻意的：
    忘記設定成本時得到的是保守的結果，而不是好看的結果。
    """

    initial_capital: float = 10_000.0
    costs: CostModel = field(default_factory=CostModel)

    def __post_init__(self) -> None:
        if self.initial_capital <= 0.0:
            raise ValueError(f"initial_capital 必須 > 0，收到 {self.initial_capital}")

    @classmethod
    def ideal(cls, initial_capital: float = 10_000.0) -> BacktestSpecification:
        """理想回測：沒有手續費、沒有滑價。當對照組用，NEVER 當結論。"""
        return cls(initial_capital=initial_capital, costs=CostModel.frictionless())
