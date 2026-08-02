# quantbot/domain/interfaces/clock.py
from typing import Protocol

import pandas as pd


class Clock(Protocol):
    """「現在幾點」。

    這是注入的能力而不是隨手可取的全域：domain 與 application 內 NEVER 直接
    呼叫 pd.Timestamp.now()。理由是可測試性——時間相關的判斷（這根收完了沒、
    批次檔上傳了沒）只要偷讀系統時間，那條路徑就再也寫不出可靠的測試。
    """

    def now(self) -> pd.Timestamp: ...
