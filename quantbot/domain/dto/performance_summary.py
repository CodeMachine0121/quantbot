# quantbot/domain/dto/performance_summary.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceSummaryDto:
    """一個策略的一頁式績效摘要。

    每一個欄位都在防一個特定的誤判，而它們**必須一起看**：

    - total_return：最沒有資訊的那一個。它不說風險、不說時間、不說曝險。
    - maximum_drawdown：從最高點跌下來最多幾成。它回答「撐不撐得過去」。
    - longest_drawdown_bars：最長多久沒有回到前一個高點。它回答「撐得過去，
      但要撐多久」——這一項最常被忽略，而它是實際上讓人放棄一個策略的原因。
    - sharpe_ratio / sortino_ratio：承擔的波動划不划算。後者只算下跌的波動，
      所以一個「往上跳得很兇」的策略不會被罰。
    - win_rate / payoff_ratio：兩個必須配對看。60% 勝率配 0.5 的賠率是賠錢的。
    - trade_count：樣本數。它決定上面每一個數字有多可信（Day 21）。
    - trial_count：試了幾次才得到這一份。它決定上面每一個數字該打幾折。

    exposure 也在裡面，因為報酬率的比較沒有它就不成立：曝險 1.35% 與 99.99% 的
    兩個策略，同樣的總報酬是完全不同的兩件事。
    """

    strategy_name: str
    trial_count: int
    bar_count: int
    trade_count: int
    exposure: float
    total_return: float
    maximum_drawdown: float
    longest_drawdown_bars: int
    sharpe_ratio: float | None
    sortino_ratio: float | None
    win_rate: float | None
    payoff_ratio: float | None

    @property
    def return_over_maximum_drawdown(self) -> float | None:
        """總報酬除以最大回撤。

        它是最粗暴但很好用的一個比率：賺到的東西跟「路上要忍受的最深一次下跌」
        的比例。回撤為零（從沒賠過）時回 None 而不是無限大。
        """
        if self.maximum_drawdown == 0.0:
            return None
        return self.total_return / abs(self.maximum_drawdown)

    def excess_over(self, baseline: PerformanceSummaryDto) -> float:
        """超額報酬：贏過基準幾個百分點。

        贏不過基準的策略沒有存在的理由——那些條件只是在製造手續費，而這件事在
        只看自己的總報酬時看不出來。
        """
        return self.total_return - baseline.total_return
