# quantbot/domain/values/sequence_decision.py
from enum import StrEnum


class SequenceDecision(StrEnum):
    """收到一筆增量更新之後，該拿它怎麼辦。

    三個選項，缺一個就會壞：

    - DISCARD：這筆的內容已經包含在快照裡了，套下去等於把時間往回撥。
    - APPLY：序號接得上，套用。
    - RESYNCHRONIZE：中間漏了幾筆，本地的簿子從這一刻起是錯的。**唯一正確的
      處理是丟掉重拉快照**，NEVER 硬套下去——漏掉的那幾筆裡可能有「某一檔被清空」，
      沒收到的話那一檔會永遠留在本地的簿子上，之後每個特徵都吃到那一檔早就不存在的掛單。
    """

    DISCARD = "discard"
    APPLY = "apply"
    RESYNCHRONIZE = "resynchronize"
