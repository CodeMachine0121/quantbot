# quantbot/domain/indicators/crossover_signals.py
from __future__ import annotations

import pandas as pd


class CrossoverSignals:
    """兩條均線的交叉事件，以及最快能成交的那一根。

    建構時就把事件算完，golden 與 death 是屬性。位移也放在這裡，因為
    「訊號怎麼算出來」與「訊號什麼時候才能用」是同一件事的兩面，拆開放
    就會有人只記得前者。

    它不是 Indicator：它吃的是兩條算好的線，不是 K 線，所以沒有繼承那個基底。
    """

    def __init__(self, fast: pd.Series, slow: pd.Series) -> None:
        ready = fast.notna() & slow.notna()
        above = (fast > slow) & ready
        previously_above = above.shift(1, fill_value=False)
        previously_ready = ready.shift(1, fill_value=False)

        # 只有狀態翻轉的那一根是 True，暖機期一律 False
        self.golden = (above & ~previously_above & previously_ready).rename("golden")
        self.death = (~above & previously_above & ready).rename("death")

    @property
    def table(self) -> pd.DataFrame:
        """兩個訊號並排，方便印出來核對或落地。"""
        return pd.concat([self.golden, self.death], axis=1)

    @property
    def entry(self) -> pd.Series:
        """黃金交叉延後一根：最快只能在下一根成交。"""
        return self.delay_to_next_bar(self.golden)

    @property
    def exit(self) -> pd.Series:
        """死亡交叉延後一根。"""
        return self.delay_to_next_bar(self.death)

    @staticmethod
    def delay_to_next_bar(signal: pd.Series) -> pd.Series:
        """把「第 t 根收盤後才知道」的訊號延後一根，代表最快在 t+1 成交。"""
        return signal.shift(1, fill_value=False).astype(bool)
