# quantbot/domain/dto/search_report.py
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class SearchTrialDto:
    """一個組合的樣本內與樣本外表現。

    兩段都要在同一列，這是這份報告的重點。分成兩張表的話，讀的人會先看樣本內
    那張的排名，而那個排名是這整件事最沒有資訊的東西。
    """

    strategy_name: str
    trade_count: int
    in_sample_sharpe: float | None
    in_sample_return: float
    out_of_sample_sharpe: float | None
    out_of_sample_return: float


@dataclass(frozen=True)
class SearchReportDto:
    """一次組合搜尋的結果。

    三個欄位是這份報告存在的理由，而它們都不是「最好的策略是哪一個」：

    - trial_count：試了幾次。少了它，樣本內的最佳結果無法解讀。
    - pruned_count：剪掉幾個。少了它，讀的人會以為搜尋涵蓋了全部組合。
    - expected_maximum_sharpe：**完全沒有預測力的 N 個組合，最好的那個大概能到
      多高。** 樣本內的最佳夏普要贏過這個數字才有得談。

    label 用來區分「真實資料」與「打亂順序的假資料」兩次搜尋。兩份報告並排放，
    Day 21 的結論就不必用嘴巴講。
    """

    label: str
    trial_count: int
    pruned_count: int
    unconstrained_combination_count: int
    in_sample_bar_count: int
    out_of_sample_bar_count: int
    periods_per_year: float
    expected_maximum_sharpe: float
    trials: tuple[SearchTrialDto, ...]

    @property
    def best_by_in_sample(self) -> SearchTrialDto:
        """樣本內夏普最高的那一個。也就是「挑最漂亮的那一個」會挑到的。"""
        ranked = [trial for trial in self.trials if trial.in_sample_sharpe is not None]
        if not ranked:
            raise ValueError("沒有任何組合算得出夏普")
        return max(ranked, key=lambda trial: trial.in_sample_sharpe or 0.0)

    @property
    def in_sample_sharpes(self) -> tuple[float, ...]:
        return tuple(
            trial.in_sample_sharpe
            for trial in self.trials
            if trial.in_sample_sharpe is not None
        )

    @property
    def best_in_sample_sharpe(self) -> float:
        return self.best_by_in_sample.in_sample_sharpe or 0.0

    @property
    def haircut(self) -> float:
        """最佳的樣本內夏普扣掉「純靠運氣能到多高」之後剩下多少。

        為負代表這個搜尋結果連雜訊的期望值都贏不過。
        """
        return self.best_in_sample_sharpe - self.expected_maximum_sharpe

    @property
    def median_in_sample_sharpe(self) -> float:
        values = self.in_sample_sharpes
        return median(values) if values else 0.0

    @property
    def survival_rate(self) -> float:
        """樣本內為正、樣本外也為正的組合佔幾成。

        它比「最佳組合的樣本外表現」穩健：後者是一個樣本，而這個是整片分布的性質。
        搜尋出來的東西如果有真的訊號，這個比例應該明顯高於一半。
        """
        promising = [
            trial
            for trial in self.trials
            if trial.in_sample_sharpe is not None and trial.in_sample_sharpe > 0.0
        ]
        if not promising:
            return 0.0
        survived = [
            trial
            for trial in promising
            if trial.out_of_sample_sharpe is not None
            and trial.out_of_sample_sharpe > 0.0
        ]
        return len(survived) / len(promising)
