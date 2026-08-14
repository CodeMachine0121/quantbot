# quantbot/domain/values/position_direction.py
from enum import StrEnum


class PositionDirection(StrEnum):
    """一個策略進場之後，部位站在哪一邊。

    部位在這個系列裡是一個**權重**而不是金額：+1 代表滿倉做多、0 代表空手、
    -1 代表滿倉做空。「一次該下多少錢」是 Day 24 的事，做成另一組積木，
    所以今天的引擎只回答方向。

    把方向做成一個值而不是直接寫 1.0 / 0.0，是為了讓「做空」這件事在型別上
    存在。本系列的主線是現貨，現貨借不到幣所以做不了空，SHORT 因此不會出現在
    任何設定檔裡——但引擎的算法對它一視同仁，走到合約時不必改引擎。
    """

    LONG = "long"
    FLAT = "flat"
    SHORT = "short"

    @property
    def weight(self) -> float:
        """換算成部位權重。回測拿這個乘上報酬。"""
        if self is PositionDirection.LONG:
            return 1.0
        if self is PositionDirection.SHORT:
            return -1.0
        return 0.0
