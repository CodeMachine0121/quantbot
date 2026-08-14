# quantbot/domain/values/comparison.py
from enum import StrEnum

import pandas as pd


class Comparison(StrEnum):
    """比大小的四種方式，以及設定檔裡代表它們的字串。

    做成一個值而不是讓每個條件各寫一次 `>`，是為了讓「合法的比較有哪幾種」變成
    列舉得出來的東西：使用者在 YAML 裡寫 `comparison: abvoe`（拼錯）時，錯誤訊息
    列得出四個合法值。四個都在這裡，NEVER 在條件類別裡再寫第二份對照表。

    含不含等於分成兩組，因為它在邊界上真的會差一根。閾值取整數（RSI 到 70）時
    尤其明顯——`above` 與 `at_least` 在 RSI 剛好等於 70 的那一根答案相反。
    """

    ABOVE = "above"
    BELOW = "below"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"

    def applies(self, left: pd.Series, right: pd.Series | float) -> pd.Series:
        """套用比較，回傳布林序列。任一邊是 NaN 的位置一律 False。

        後面這半句不是這裡寫的，是 pandas 的比較運算本來就這樣。而它剛好是這個
        系列要的語意：答不出來的時候不成立。
        """
        if self is Comparison.ABOVE:
            return left > right
        if self is Comparison.BELOW:
            return left < right
        if self is Comparison.AT_LEAST:
            return left >= right
        return left <= right

    @property
    def symbol(self) -> str:
        """給 describe() 用的數學符號。"""
        return {
            Comparison.ABOVE: ">",
            Comparison.BELOW: "<",
            Comparison.AT_LEAST: ">=",
            Comparison.AT_MOST: "<=",
        }[self]
