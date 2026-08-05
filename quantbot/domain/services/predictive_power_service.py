# quantbot/domain/services/predictive_power_service.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.dto.predictive_power_report import PredictivePowerReportDto


class PredictivePowerService:
    """量一個特徵對未來報酬有沒有資訊。

    這是本系列第一個「判斷特徵值不值得用」的工具，而它要先擋掉兩件事：

    1. **未來函數。** 未來報酬一定是用 shift(-horizon) 往後看，而特徵是當下的值。
       兩者對齊錯一格，就會拿「當下的報酬」去解釋「當下的特徵」，相關係數會漂亮
       得不像話。這裡的對齊只寫在 forward_returns() 一份。
    2. **看起來有效其實是樣本太少。** 相關係數在小樣本上天生就會偏離 0，所以報告
       裡一定要有樣本數與 t 值，NEVER 只印一個相關係數。

    用 Spearman 而不是 Pearson：報酬的分布有厚尾，Pearson 會被幾個極端值主導。
    Spearman 只看排序，回答的是「特徵大的時候報酬是否傾向比較大」——這正是問題。
    """

    def __init__(self, *, bucket_count: int = 5) -> None:
        if bucket_count < 2:
            raise ValueError(f"bucket_count 必須 >= 2，收到 {bucket_count}")
        self._bucket_count = bucket_count

    @property
    def bucket_count(self) -> int:
        return self._bucket_count

    @staticmethod
    def forward_returns(
        prices: pd.Series, *, horizon: int, maximum_step: pd.Timedelta | None = None
    ) -> pd.Series:
        """往後 horizon 格的報酬率，對齊到「現在」這一格。

        shift(-horizon) 是這整套驗證唯一允許往未來看的地方，而它必須出現在
        被解釋的那一側（報酬），NEVER 出現在特徵那一側。特徵一旦偷看未來，
        後面所有數字都是假的，而且看起來會特別好。

        maximum_step 處理的是另一個問題：**shift() 只認得「第幾格」，不認得時間。**
        掛單簿的取樣是不規則的，而且錄製中斷過的話中間會有一段空白。那時候
        shift(-1) 會把空白前後的兩筆配成一對，於是一個「往後一秒」的報酬實際上
        跨了二十幾分鐘。這種列不多，但它們的報酬大得離譜，足以主導相關係數。

        給了 maximum_step 就把間隔過大的配對變成 NaN。這是 K 線不會遇到、
        而不規則取樣一定會遇到的事，所以它是參數而不是預設行為。
        """
        if horizon < 1:
            raise ValueError(f"horizon 必須 >= 1，收到 {horizon}")
        returns = prices.shift(-horizon) / prices - 1.0
        if maximum_step is not None:
            times = pd.Series(pd.DatetimeIndex(prices.index), index=prices.index)
            elapsed = times.shift(-horizon) - times
            returns = returns.where(elapsed <= maximum_step)
        return returns.rename(f"forward_{horizon}")

    def evaluate(
        self, feature: pd.Series, forward: pd.Series
    ) -> PredictivePowerReportDto:
        paired = pd.concat({"feature": feature, "forward": forward}, axis=1).dropna()
        if len(paired) < self._bucket_count * 2:
            raise ValueError(
                f"樣本只有 {len(paired)} 筆，分不出 {self._bucket_count} 組"
            )

        coefficient = self.rank_correlation(paired["feature"], paired["forward"])
        return PredictivePowerReportDto(
            feature_name=str(feature.name),
            sample_count=len(paired),
            horizon=self._horizon_of(forward),
            information_coefficient=coefficient,
            t_statistic=self._t_statistic(coefficient, len(paired)),
            bucket_mean_returns=self._bucket_mean_returns(paired),
        )

    @staticmethod
    def rank_correlation(feature: pd.Series, forward: pd.Series) -> float:
        """Spearman 相關係數，用定義算：**先取排名，再算 Pearson**。

        pandas 的 corr(method="spearman") 會轉去呼叫 scipy，而這個專案沒有 scipy
        這個依賴。與其為了一行相關係數多裝一整包，不如照定義寫——Spearman 本來就
        是「排名上的 Pearson」，這樣寫出來的程式碼還比呼叫別人的更說明它在做什麼。

        rank() 預設用平均排名處理同分，跟 scipy 的預設一致。這件事對 OBI 很重要：
        它有大量的值落在 ±1（某一側被清空），同分處理方式不同會改變結果。
        """
        return float(feature.rank().corr(forward.rank()))

    def _bucket_mean_returns(self, paired: pd.DataFrame) -> tuple[float, ...]:
        """按特徵值分成等量的幾組，各組的平均未來報酬。

        用 qcut（等量分組）而不是 cut（等寬分組）：OBI 的分布集中在中間，
        等寬分組會讓最外面兩組各只有幾十筆，那兩組的平均值就只是雜訊。
        duplicates="drop" 是必要的——特徵值重複太多時分位點會撞在一起。
        """
        buckets = pd.qcut(
            paired["feature"], self._bucket_count, labels=False, duplicates="drop"
        )
        grouped = paired["forward"].groupby(buckets).mean().sort_index()
        return tuple(float(value) for value in grouped)

    @staticmethod
    def _t_statistic(coefficient: float, sample_count: int) -> float:
        """相關係數的 t 值。|t| 小於 2 的話，這個相關性跟 0 分不出來。

        它不是「這個特徵能不能賺錢」的答案，只是「這個數字是不是雜訊」的下限檢查。
        """
        if sample_count <= 2 or abs(coefficient) >= 1.0:
            return float("nan")
        return float(
            coefficient * np.sqrt(sample_count - 2) / np.sqrt(1.0 - coefficient**2)
        )

    @staticmethod
    def _horizon_of(forward: pd.Series) -> int:
        """從序列名字取回 horizon。forward_returns() 產生的名字是 forward_{n}。"""
        name = str(forward.name)
        return int(name.rsplit("_", 1)[-1]) if name.startswith("forward_") else 0
