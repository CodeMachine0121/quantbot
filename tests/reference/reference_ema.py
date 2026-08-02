# tests/reference/reference_ema.py
"""照定義手寫的遞迴參考實作，只在測試裡當對照組使用。

刻意用 Python 迴圈寫，不追求效能，它的價值在於好讀、好對照數學式。
它 NEVER 進正式路徑——`quantbot/` 底下不會 import 這個檔案。
Day 26 會把同一條迴圈交給 Numba 編譯，並用這裡的數字當正確性基準。
"""

from __future__ import annotations

import numpy as np


class ReferenceEMA:
    """一根一根滾出 EMA。與 quantbot 的 EMA 同一組設定、同一個 alpha 公式。"""

    def __init__(self, period: int, *, warmup: str = "sma") -> None:
        self.period = period
        self.warmup = warmup
        self.alpha = 2.0 / (period + 1)

    def compute(self, values: np.ndarray) -> np.ndarray:
        """回傳與輸入等長的 float64 陣列，暖機期是 NaN。"""
        out = np.full(values.shape, np.nan, dtype="float64")

        if self.warmup == "sma":
            if values.size < self.period:
                return out
            start = self.period - 1
            previous = float(values[: self.period].mean())
        else:
            if values.size == 0:
                return out
            start = 0
            previous = float(values[0])

        out[start] = previous
        for index in range(start + 1, values.size):
            previous = self.alpha * float(values[index]) + (1 - self.alpha) * previous
            out[index] = previous
        return out
