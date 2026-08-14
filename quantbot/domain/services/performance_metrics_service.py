# quantbot/domain/services/performance_metrics_service.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.dto.backtest_report import BacktestReportDto
from quantbot.domain.dto.performance_summary import PerformanceSummaryDto


class PerformanceMetricsService:
    """從報酬序列算出績效指標。

    Day 21 只用到夏普（搜尋需要一個單一數字排名），其餘指標 Day 22 補上——
    那一天的主題正是「單一數字排名為什麼會誤導」。所有指標都掛在同一個 service 上，
    因為它們吃的是同一份原料（報酬序列與交易明細），而分開放會讓「這些數字是不是
    同一段資料算出來的」變成一個要靠人記得的事。

    年化用「一年有幾根」換算，而那個數字由 timeframe 決定，所以它是參數而不是
    常數。1 小時 K 線一年 8,760 根，1 天 K 線 365 根，差 24 倍——寫死任何一個
    都會讓另一個的夏普錯 4.9 倍（根號 24）。
    """

    def sharpe_ratio(
        self, returns: pd.Series, *, periods_per_year: float
    ) -> float | None:
        """年化夏普比率。無風險利率取 0。

        回 None 而不是 0 或 inf 的三種情況：樣本太少（少於兩筆）、標準差為零
        （完全沒有交易的策略，報酬全是 0）、以及標準差算出 NaN。這三種都不是
        「夏普很差」，是「夏普沒有定義」，而把它們當成 0 會讓一個從不交易的策略
        排在賠錢的策略前面。

        無風險利率取 0 是這個系列的簡化，而它在加密貨幣上比在股票上合理——
        這裡的比較對象是「同一段時間的其他策略」，而不是「放定存」。
        """
        cleaned = returns.dropna()
        if len(cleaned) < 2:
            return None
        deviation = float(cleaned.std(ddof=1))
        if deviation == 0.0 or not np.isfinite(deviation):
            return None
        return float(cleaned.mean()) / deviation * float(np.sqrt(periods_per_year))

    def maximum_drawdown(self, equity: pd.Series) -> float:
        """從歷史最高點跌下來最深的一次，回傳負數（-0.35 就是跌了 35%）。

        用權益曲線而不是報酬序列，因為回撤是一個**路徑**性質：同一組報酬換個順序
        會得到完全不同的最大回撤，而那正是它要量的東西。
        """
        cleaned = equity.dropna()
        if cleaned.empty:
            return 0.0
        peak = cleaned.cummax()
        return float((cleaned / peak - 1.0).min())

    def longest_drawdown_bars(self, equity: pd.Series) -> int:
        """最長有幾根沒有回到前一個高點。

        它是最常被忽略的一個指標，而它是實際上讓人放棄一個策略的原因：
        一個回撤 20% 但兩週就收復的策略，跟一個回撤 20% 但拖了八個月的策略，
        數字上一樣，忍受度完全不同。

        還沒收復的那一段也要算進來（結尾那段的長度就是它的長度），
        否則一個「跌下去就再也沒回來」的策略會回一個很小的數字。
        """
        cleaned = equity.dropna()
        if cleaned.empty:
            return 0
        at_peak = cleaned >= cleaned.cummax()
        longest = 0
        current = 0
        for peaked in at_peak.to_numpy():
            current = 0 if peaked else current + 1
            longest = max(longest, current)
        return longest

    def sortino_ratio(
        self, returns: pd.Series, *, periods_per_year: float
    ) -> float | None:
        """只用下跌的波動當分母的夏普。

        夏普會處罰「往上跳得很兇」的策略，而那不是風險。索提諾只算負報酬的
        標準差，所以它比較貼近「痛的部分」。

        沒有任何負報酬時回 None 而不是無限大——那種情況多半是樣本太少，
        而一個無限大的排名值會讓它衝到榜首。
        """
        cleaned = returns.dropna()
        if len(cleaned) < 2:
            return None
        losses = cleaned[cleaned < 0.0]
        if len(losses) < 2:
            return None
        downside = float(losses.std(ddof=1))
        if downside == 0.0 or not np.isfinite(downside):
            return None
        return float(cleaned.mean()) / downside * float(np.sqrt(periods_per_year))

    def win_rate(self, trades: pd.DataFrame) -> float | None:
        """賺錢的交易佔幾成。用**淨**報酬判斷，不是毛報酬。

        用毛報酬算勝率會系統性地高估：一筆賺 0.1% 的交易在扣掉 0.3% 來回成本
        之後是虧的，而它在毛報酬的帳上是「贏」。
        """
        if trades.empty:
            return None
        return float((trades["net_return"] > 0.0).mean())

    def payoff_ratio(self, trades: pd.DataFrame) -> float | None:
        """平均獲利除以平均虧損（取絕對值）。

        它必須跟勝率配對看。**60% 勝率配 0.5 的賠率是賠錢的**：
        0.6 × 1 − 0.4 × 2 = −0.2。只看勝率的排行榜會把這種策略排在前面。

        沒有虧損單或沒有獲利單時回 None：那時候這個比率不是「很好」，是沒有定義，
        而樣本大一點之後它一定會出現另一邊。
        """
        if trades.empty:
            return None
        wins = trades.loc[trades["net_return"] > 0.0, "net_return"]
        losses = trades.loc[trades["net_return"] < 0.0, "net_return"]
        if wins.empty or losses.empty:
            return None
        average_loss = abs(float(losses.mean()))
        if average_loss == 0.0:
            return None
        return float(wins.mean()) / average_loss

    def summarize(
        self, report: BacktestReportDto, *, periods_per_year: float
    ) -> PerformanceSummaryDto:
        """一份回測結果收成一頁摘要。

        trial_count 從回測報告直接帶過來，NEVER 在這裡重新給一個預設值——
        它是 Day 19 那個「沒有預設值」的欄位，而摘要是最常被單獨拿出去看的東西。
        """
        return PerformanceSummaryDto(
            strategy_name=report.strategy_name,
            trial_count=report.trial_count,
            bar_count=report.bar_count,
            trade_count=report.trade_count,
            exposure=report.exposure,
            total_return=report.total_return,
            maximum_drawdown=self.maximum_drawdown(report.equity),
            longest_drawdown_bars=self.longest_drawdown_bars(report.equity),
            sharpe_ratio=self.sharpe_ratio(
                report.returns, periods_per_year=periods_per_year
            ),
            sortino_ratio=self.sortino_ratio(
                report.returns, periods_per_year=periods_per_year
            ),
            win_rate=self.win_rate(report.trades),
            payoff_ratio=self.payoff_ratio(report.trades),
        )

    def monthly_returns(self, equity: pd.Series) -> pd.Series:
        """每個月的報酬率，給熱力圖用。

        用月底的權益相除而不是把日報酬加總：加總會忽略複利，而在月報酬有正有負的
        時候那個誤差不是四捨五入的等級。
        """
        cleaned = equity.dropna()
        if cleaned.empty:
            return pd.Series(dtype="float64", name="monthly_return")

        monthly = cleaned.resample("ME").last()
        opening = monthly.shift(1)
        # 第一個月沒有「上個月底」，它的起點是整段資料的第一個權益值
        opening.iloc[0] = float(cleaned.iloc[0])
        ratios = monthly.to_numpy(dtype="float64") / opening.to_numpy(dtype="float64")
        return pd.Series(
            ratios - 1.0, index=monthly.index, dtype="float64", name="monthly_return"
        )
