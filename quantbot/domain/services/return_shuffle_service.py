# quantbot/domain/services/return_shuffle_service.py
from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries


class ReturnShuffleService:
    """把真實報酬的順序打亂，重建一條「完全沒有訊號」的價格走勢。

    這是 Day 21 那個示範的資料來源，而它比「用隨機數產生價格」好，理由是它保留了
    真實資料的分布：一樣的報酬平均值、一樣的標準差、一樣的厚尾、一樣的極端值。
    被破壞的只有**順序**——而所有技術分析的訊號都建在順序上（趨勢是順序、
    交叉是順序、突破是順序）。

    所以打亂之後的資料有一個很好的性質：**任何依賴順序的策略在上面都不該有效**，
    而其他條件全部相同。在那樣的資料上還「找得到」漂亮的策略，就只能是搜尋本身
    的問題。

    亂數種子是參數而不是全域狀態。理由跟 Day 07 的 Clock 一樣：偷讀全域狀態的
    程式碼寫不出可靠的測試，而「同一個種子產生同一段假資料」是這個示範可以被
    重現的前提。
    """

    def shuffled_prices(self, close: pd.Series, *, seed: int) -> pd.Series:
        """回一條與輸入等長、index 相同、起點相同的假價格序列。

        用對數報酬打亂再累積，而不是直接打亂價格：後者會產生一條到處跳的鋸齒，
        而那個東西的波動率跟原始資料差好幾倍，比較就不公平了。
        """
        if len(close) < 3:
            raise ValueError(f"至少要 3 根才打得亂，收到 {len(close)}")

        values = close.astype("float64").to_numpy()
        if (values <= 0.0).any():
            raise ValueError("價格必須為正才取得對數報酬")

        log_returns = np.diff(np.log(values))
        generator = np.random.default_rng(seed)
        shuffled = generator.permutation(log_returns)
        rebuilt = values[0] * np.exp(np.concatenate(([0.0], np.cumsum(shuffled))))
        return pd.Series(rebuilt, index=close.index, dtype="float64", name=close.name)

    def shuffled_candles(self, series: CandleSeries, *, seed: int) -> CandleSeries:
        """把整串 K 線的收盤價換成打亂重建的版本，其餘欄位按比例跟著走。

        開高低乘上「新收盤價除以舊收盤價」這個比例，而不是設成等於收盤價：後者會
        讓每一根變成一條線，ATR 之類看高低價的特徵就全部歸零，而那不是「沒有訊號」，
        那是「另一種資料」。按比例縮放保留了每一根的相對影線長度。

        成交量與筆數原封不動。它們的順序也被打亂會更徹底，但那樣就有兩個變數同時
        改變，而這個示範要問的是「順序被破壞之後還找得到策略嗎」，變數越少越好。
        """
        candles = series.frame
        shuffled_close = self.shuffled_prices(candles["close"], seed=seed)
        factor = shuffled_close / candles["close"]

        rebuilt = candles.copy()
        for column in ("open", "high", "low"):
            rebuilt[column] = candles[column] * factor
        rebuilt["close"] = shuffled_close
        return CandleSeries(series.instrument, rebuilt)
