# quantbot/domain/services/trial_deflation_service.py
from __future__ import annotations

import numpy as np


class TrialDeflationService:
    """試了 N 次之後，「最好的那個夏普」有多少是運氣。

    直覺是這樣：即使每一個組合都完全沒有預測力，它們的夏普估計值也不會剛好是 0——
    每一個都有估計誤差，所以會散在 0 附近。試 N 次就是抽 N 個樣本，而**取最大值**
    這個動作會系統性地挑到誤差最大的那一個。N 越大，那個最大值越高，跟策略好壞
    完全無關。

    所以「跑 500 個組合挑最漂亮的那一個」的問題不是效率，是**取最大值本身就是
    一個偏誤來源**。要判斷一個搜尋結果值不值得看，得先知道「純靠運氣能到多高」。

    這裡用的是最粗的近似：N 個標準常態的最大值期望值約為 sqrt(2 ln N)。
    真正的 deflated Sharpe ratio 還會處理報酬的偏態、峰態與試驗之間的相關性，
    公式長很多，而這個系列要的是**量級**而不是小數點。等一下 Day 21 會用打亂順序的
    假資料實測一次，看這個近似估得準不準。
    """

    def standard_error(
        self, *, observation_count: int, periods_per_year: float
    ) -> float:
        """年化夏普的估計標準誤，約等於 1 除以「幾年的資料」的平方根。

        它是這整件事的關鍵尺度：同一個夏普值，在半年的資料上與在十年的資料上
        可信度完全不同，而只印夏普看不出差別。
        """
        if observation_count < 2:
            raise ValueError(f"observation_count 必須 >= 2，收到 {observation_count}")
        years = observation_count / periods_per_year
        return float(np.sqrt(1.0 / years))

    def expected_maximum_sharpe(
        self, *, trial_count: int, observation_count: int, periods_per_year: float
    ) -> float:
        """N 個「其實沒有預測力」的組合裡，最好的那個夏普大概會是多少。

        搜尋結果要贏過這個數字才有得談。贏不過的話，那個結果跟「在雜訊裡挑最大值」
        沒有分別——而挑最大值一定挑得到東西。
        """
        if trial_count < 1:
            raise ValueError(f"trial_count 必須 >= 1，收到 {trial_count}")
        if trial_count == 1:
            return 0.0
        error = self.standard_error(
            observation_count=observation_count, periods_per_year=periods_per_year
        )
        return float(np.sqrt(2.0 * np.log(trial_count))) * error

    def haircut(
        self,
        observed_sharpe: float,
        *,
        trial_count: int,
        observation_count: int,
        periods_per_year: float,
    ) -> float:
        """把「純靠運氣能到多高」從觀察到的夏普裡扣掉。

        結果為負代表這個搜尋結果連雜訊的期望值都贏不過。它不是「策略比較差」，
        是「這個數字沒有資訊」。
        """
        return observed_sharpe - self.expected_maximum_sharpe(
            trial_count=trial_count,
            observation_count=observation_count,
            periods_per_year=periods_per_year,
        )
