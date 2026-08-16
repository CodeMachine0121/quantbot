# quantbot/domain/services/walk_forward_service.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    """一段樣本內加上緊接在後的樣本外。

    兩段**必須相鄰而且不重疊**，這是這個值唯一的不變式，也是它存在的理由：
    樣本內外重疊一根，樣本外就不再是樣本外了，而那種錯誤在一張時間區間表上
    看不出來。
    """

    in_sample: pd.DatetimeIndex
    out_of_sample: pd.DatetimeIndex

    def __post_init__(self) -> None:
        if len(self.in_sample) == 0 or len(self.out_of_sample) == 0:
            raise ValueError("樣本內與樣本外都不能是空的")
        if self.in_sample.max() >= self.out_of_sample.min():
            raise ValueError("樣本外必須完全在樣本內之後")


class WalkForwardService:
    """把一段時間軸切成「調參數的那段」與「驗證的那段」。

    為什麼不能只切一次：切一次的話，樣本外只有一段特定的市況（我們這份資料的
    後段剛好是下跌），而一個「在下跌市場裡表現好」的策略會被誤認為穩健。滾動切
    成幾折之後，每一折的樣本外是不同的市況，一致性才問得出來。

    它只回索引，不碰資料也不算績效。切法與評估分開的好處是切法可以單獨測——
    而「樣本外有沒有偷到樣本內的資料」這件事只有切法測得出來。
    """

    def split(
        self, index: pd.DatetimeIndex, *, in_sample_fraction: float = 0.7
    ) -> WalkForwardFold:
        """切一刀：前面調參數，後面驗證。"""
        if not 0.0 < in_sample_fraction < 1.0:
            raise ValueError(
                f"in_sample_fraction 必須在 0 與 1 之間，收到 {in_sample_fraction}"
            )
        cut = int(len(index) * in_sample_fraction)
        if cut < 1 or cut >= len(index):
            raise ValueError(f"{len(index)} 根切不出兩段非空的資料")
        return WalkForwardFold(in_sample=index[:cut], out_of_sample=index[cut:])

    def folds(
        self,
        index: pd.DatetimeIndex,
        *,
        fold_count: int,
        in_sample_fraction: float = 0.7,
    ) -> tuple[WalkForwardFold, ...]:
        """滾動切成幾折，每一折的樣本外接在自己的樣本內後面。

        切法是「把整段等分成 fold_count 塊，第 k 折用前 k 塊當一個窗」——也就是
        錨定式（anchored）：樣本內只會變長，不會滑掉開頭。這個選擇對參數穩定性
        比較寬容，而它的替代方案（固定長度的滑動窗）對「舊資料還算不算數」的
        假設不同。兩種都合理，但要說清楚用的是哪一種。
        """
        if fold_count < 1:
            raise ValueError(f"fold_count 必須 >= 1，收到 {fold_count}")
        block = len(index) // (fold_count + 1)
        if block < 2:
            raise ValueError(f"{len(index)} 根切不出 {fold_count} 折")

        built: list[WalkForwardFold] = []
        for fold in range(1, fold_count + 1):
            window = index[: block * (fold + 1)]
            built.append(self.split(window, in_sample_fraction=in_sample_fraction))
        return tuple(built)
