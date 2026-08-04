# quantbot/domain/services/order_book_sequence_service.py
from __future__ import annotations

from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.sequence_decision import SequenceDecision


class OrderBookSequenceService:
    """判斷一筆增量更新該套用、該丟掉，還是該重新拉快照。

    這是整個即時資料路徑最容易寫錯、而且錯了最難察覺的一段規則，所以它獨立成一個
    domain service：不碰網路、不碰狀態、只吃兩個數字與一筆更新，回傳一個決定。
    它因此可以用一張表把所有情況列完並測完，不需要開任何連線。

    規則有兩段，分別對應「剛接上」與「已經在跑」兩種處境：

    - 第一筆（still_synchronizing 為真）：更新的區間必須**跨過**快照的序號，
      也就是 first <= snapshot + 1 <= final。跨不過的話有兩種可能——整個區間都在
      快照之前（內容已經包含在快照裡，丟掉），或整個區間都在快照之後（中間漏了，
      快照已經追不上，重拉）。
    - 之後每一筆：first 必須正好等於本地序號 + 1。
    """

    def decide(
        self,
        local_update_id: int,
        update: OrderBookUpdate,
        *,
        still_synchronizing: bool,
    ) -> SequenceDecision:
        if update.final_update_id <= local_update_id:
            # 整個區間都在本地序號之前：這筆的內容已經反映在簿子上了。
            # 套下去等於把時間往回撥，會把之後才被撤掉的掛單又放回來。
            return SequenceDecision.DISCARD

        if still_synchronizing:
            covers_snapshot = update.first_update_id <= local_update_id + 1
            return (
                SequenceDecision.APPLY
                if covers_snapshot
                else SequenceDecision.RESYNCHRONIZE
            )

        return (
            SequenceDecision.APPLY
            if update.first_update_id == local_update_id + 1
            else SequenceDecision.RESYNCHRONIZE
        )
