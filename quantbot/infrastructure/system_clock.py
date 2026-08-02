# quantbot/infrastructure/system_clock.py
import pandas as pd


class SystemClock:
    """讀系統時間。實作 domain 的 Clock。

    這是全專案唯一允許呼叫 pd.Timestamp.now() 的地方（entrypoints 除外），
    所以「時間從哪裡來」只有一個答案。
    """

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz="UTC")
