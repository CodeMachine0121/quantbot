# quantbot/domain/dto/predictive_power_report.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PredictivePowerReportDto:
    """一個特徵對未來報酬有沒有資訊，攤成幾個看得懂的數字。

    刻意不提供 passed 這種布林值。前面幾天的報告（資料完整性、逐欄對帳）可以有
    通過與不通過，因為那些是對錯問題。這裡不是——「IC 0.03 算不算有用」取決於
    交易成本、訊號頻率、部位大小，而那三件事到 Day 20 與 Day 24 才會定下來。
    現在給一個門檻，只會變成一個被拿去當結論的魔術數字。
    """

    feature_name: str
    sample_count: int
    horizon: int
    information_coefficient: float
    t_statistic: float
    bucket_mean_returns: tuple[float, ...]

    @property
    def top_minus_bottom(self) -> float:
        """最高組與最低組的未來報酬差。它是這張報告裡最接近「賺得到嗎」的數字。"""
        if not self.bucket_mean_returns:
            return float("nan")
        return self.bucket_mean_returns[-1] - self.bucket_mean_returns[0]

    @property
    def is_monotonic(self) -> bool:
        """分組報酬是不是隨著特徵值單調遞增。

        單調比「頭尾差很大」更能說明這個特徵有資訊：頭尾差大但中間亂跳，
        通常表示那個差距來自少數幾個極端值，換一段樣本就不見了。
        """
        returns = pd.Series(self.bucket_mean_returns)
        return bool(returns.is_monotonic_increasing) and len(returns) > 1
