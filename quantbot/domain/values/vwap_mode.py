# quantbot/domain/values/vwap_mode.py
from enum import StrEnum


class VWAPMode(StrEnum):
    """VWAP 的累積範圍：每天重置，還是固定視窗往前滾。

    兩者是不同的工具，不是同一個工具的兩種設定：

    - SESSION：從當日開盤累積到現在。它是**當天所有參與者的平均成本**，所以
      「價格在 VWAP 之上」對今天進場的人有意義。代價是它在一天剛開始時只用了
      幾根 K 線，很不穩，而且跨日會跳。
    - ROLLING：固定往前看 N 根。它不認識「一天」這個概念，所以在 24/7 的加密貨幣
      市場上比較自然，也不會有跨日跳動；代價是它不對應任何一群人的實際成本。

    加密貨幣沒有收盤，所謂「當日」是人為切的 UTC 午夜。這件事要講清楚——
    它是一個約定，不是市場的性質。
    """

    SESSION = "session"
    ROLLING = "rolling"
