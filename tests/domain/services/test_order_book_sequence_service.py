import pandas as pd
import pytest

from quantbot.domain.services.order_book_sequence_service import (
    OrderBookSequenceService,
)
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.sequence_decision import SequenceDecision

EVENT_TIME = pd.Timestamp("2026-07-15T00:00:00Z")


def update(first: int, final: int) -> OrderBookUpdate:
    return OrderBookUpdate(
        event_time=EVENT_TIME,
        first_update_id=first,
        final_update_id=final,
        bid_changes=(),
        ask_changes=(),
    )


@pytest.mark.parametrize(
    ("local", "first", "final", "synchronizing", "expected"),
    [
        # 剛接上：更新的區間跨過快照序號，這是唯一可以開始套用的情況
        (100, 95, 105, True, SequenceDecision.APPLY),
        (100, 101, 110, True, SequenceDecision.APPLY),  # 正好接在後面
        # 整段都在快照之前：內容已經包含在快照裡
        (100, 90, 99, True, SequenceDecision.DISCARD),
        (100, 90, 100, True, SequenceDecision.DISCARD),  # 邊界：final == local
        # 剛接上就已經跳過去了：快照追不上，只能重拉
        (100, 102, 110, True, SequenceDecision.RESYNCHRONIZE),
        # 已經在跑：first 必須正好是 local + 1
        (100, 101, 105, False, SequenceDecision.APPLY),
        (100, 103, 105, False, SequenceDecision.RESYNCHRONIZE),
        (100, 99, 105, False, SequenceDecision.RESYNCHRONIZE),  # 重疊也不接受
        (100, 95, 98, False, SequenceDecision.DISCARD),
    ],
)
def test_decision_table(local, first, final, synchronizing, expected):
    decision = OrderBookSequenceService().decide(
        local, update(first, final), still_synchronizing=synchronizing
    )
    assert decision is expected


def test_a_continuous_stream_is_always_applied():
    """連續的更新流一筆都不該被丟掉，也不該觸發重拉。

    這個測試存在的理由是防「校驗寫太嚴」：把條件寫成 first > local 之類的話，
    上面那張表可能還是全過，但正常流量會每一筆都要求重拉。
    """
    service = OrderBookSequenceService()
    local = 1_000
    synchronizing = True

    for step in range(50):
        current = update(local + 1, local + 3)
        decision = service.decide(local, current, still_synchronizing=synchronizing)
        assert decision is SequenceDecision.APPLY, f"第 {step} 筆被拒絕"
        local = current.final_update_id
        synchronizing = False
