from collections.abc import AsyncIterator
from unittest.mock import create_autospec

import pandas as pd
import pytest

from quantbot.application.record_microstructure_application import (
    RecordMicrostructureApplication,
)
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.interfaces.clock import Clock
from quantbot.domain.interfaces.depth_repository import DepthRepository
from quantbot.domain.interfaces.order_book_snapshot_source import (
    OrderBookSnapshotSource,
)
from quantbot.domain.interfaces.order_book_stream import OrderBookStream
from quantbot.domain.interfaces.trade_repository import TradeRepository
from quantbot.domain.interfaces.trade_stream import TradeStream
from quantbot.domain.services.order_book_sequence_service import (
    OrderBookSequenceService,
)
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.price_level import PriceLevel
from quantbot.domain.values.recording_configuration import RecordingConfiguration
from quantbot.domain.values.trade_event import TradeEvent

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
START = pd.Timestamp("2026-07-15T00:00:00Z")


class SteppingClock:
    """每問一次就往前走一格的時鐘。

    這是測試 helper，所以可以是這種形狀（正式路徑上的時鐘是 SystemClock）。
    用它而不是 freezegun：時間本來就是注入的能力，不需要 monkeypatch 系統時鐘。
    """

    def __init__(self, *, step_seconds: float = 0.4) -> None:
        self._step = pd.Timedelta(seconds=step_seconds)
        self._now = START

    def now(self) -> pd.Timestamp:
        current = self._now
        self._now = self._now + self._step
        return current


def snapshot(last_update_id: int) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        last_update_id=last_update_id,
        bids=tuple(PriceLevel(99.0 - index, 1.0) for index in range(25)),
        asks=tuple(PriceLevel(101.0 + index, 1.0) for index in range(25)),
    )


def update(first: int, final: int) -> OrderBookUpdate:
    return OrderBookUpdate(
        event_time=START,
        first_update_id=first,
        final_update_id=final,
        bid_changes=(PriceLevel(99.0, 2.0),),
        ask_changes=(PriceLevel(101.0, 3.0),),
    )


def trade_event(trade_id: int) -> TradeEvent:
    return TradeEvent(
        transact_time=START + pd.Timedelta(seconds=trade_id),
        trade_id=trade_id,
        first_trade_id=trade_id,
        last_trade_id=trade_id,
        price=100.0 + trade_id,
        quantity=0.5,
        buyer_is_maker=trade_id % 2 == 0,
    )


def build(
    *,
    updates: list[OrderBookUpdate],
    events: list[TradeEvent],
    configuration: RecordingConfiguration | None = None,
):
    async def update_iterator(_: Listing) -> AsyncIterator[OrderBookUpdate]:
        for item in updates:
            yield item

    async def event_iterator(_: Listing) -> AsyncIterator[TradeEvent]:
        for item in events:
            yield item

    trades = create_autospec(TradeStream, spec_set=True, instance=True)
    trades.events.side_effect = event_iterator
    order_book = create_autospec(OrderBookStream, spec_set=True, instance=True)
    order_book.updates.side_effect = update_iterator

    snapshots = create_autospec(OrderBookSnapshotSource, spec_set=True, instance=True)
    snapshots.snapshot.side_effect = [snapshot(100), snapshot(500), snapshot(900)]

    trade_repository = create_autospec(TradeRepository, spec_set=True, instance=True)
    trade_repository.save.side_effect = lambda series, **_keywords: len(series)
    depth_repository = create_autospec(DepthRepository, spec_set=True, instance=True)
    depth_repository.save.side_effect = len

    clock = create_autospec(Clock, spec_set=True, instance=True)
    clock.now.side_effect = SteppingClock().now

    application = RecordMicrostructureApplication(
        configuration or RecordingConfiguration(listing=LISTING, duration_seconds=5.0),
        trades=trades,
        order_book=order_book,
        snapshots=snapshots,
        trade_repository=trade_repository,
        depth_repository=depth_repository,
        sequence=OrderBookSequenceService(),
        clock=clock,
    )
    return application, snapshots, trade_repository, depth_repository


async def test_records_both_streams_and_flushes_at_the_end():
    updates = [update(101 + index * 2, 102 + index * 2) for index in range(10)]
    application, snapshots, trade_repository, depth_repository = build(
        updates=updates, events=[trade_event(index) for index in range(6)]
    )

    report = await application.run()

    assert report.recorded_trade_count == 6
    assert report.applied_update_count == 10
    assert report.resynchronization_count == 0
    assert report.recorded_depth_row_count > 0
    snapshots.snapshot.assert_awaited_once()  # 沒有斷裂就只拉一次快照
    trade_repository.save.assert_awaited_once()  # 攢一批再寫，不是逐筆
    depth_repository.save.assert_awaited_once()


async def test_no_update_means_no_snapshot_was_ever_requested():
    """訂閱先、快照後。這個順序寫反的代價是每次啟動都多一次重拉。

    一筆更新都沒收到的話，代表訂閱根本沒成功，那時候拉快照是白花 5 weight——
    而且它會讓「啟動時的 resynchronization_count 應該是 0」這個健康指標失效。
    """
    application, snapshots, _, _ = build(updates=[], events=[trade_event(1)])

    report = await application.run()

    snapshots.snapshot.assert_not_awaited()
    assert report.resynchronization_count == 0


async def test_a_sequence_gap_pulls_a_fresh_snapshot():
    """漏了幾筆之後 NEVER 硬套下去，要重拉快照。

    第二筆 (521, 522) 跟本地序號 102 之間空了一段，所以它不被套用，而是換一份
    序號 500 的新快照。第三筆 (501, 502) 跨過 500，於是新快照從它開始接上——
    重拉之後那個「跨過快照序號」的判斷會再走一次，這是接續正確的關鍵。
    """
    updates = [update(101, 102), update(521, 522), update(501, 502)]
    application, snapshots, _, _ = build(updates=updates, events=[])

    report = await application.run()

    assert report.resynchronization_count == 1
    assert report.applied_update_count == 2  # 斷裂前一筆 ＋ 重拉後接上的那筆
    assert snapshots.snapshot.await_count == 2  # 起始一次 ＋ 重取一次


async def test_a_gap_the_fresh_snapshot_cannot_cover_resynchronizes_again():
    """重拉之後仍然接不上的話，就要再重拉一次。

    序號 500 的新快照配上 (901, 902) 這筆更新：中間空了整整四百，快照本身
    已經落後太多。這裡的正確行為是再換一份，NEVER 因為「剛剛才拉過」就將就。
    第三份快照的序號是 900，終於跨得過去。
    """
    updates = [update(901, 902) for _ in range(3)]
    application, snapshots, _, _ = build(updates=updates, events=[])

    report = await application.run()

    assert report.resynchronization_count == 2
    assert report.applied_update_count == 1  # 第三份快照（900）終於接上
    assert snapshots.snapshot.await_count == 3


async def test_stale_updates_are_discarded_not_applied():
    """序號比快照舊的更新要丟掉。套下去會把已經撤掉的掛單放回來。"""
    updates = [update(50, 60), update(70, 90), update(101, 102)]
    application, snapshots, _, _ = build(updates=updates, events=[])

    report = await application.run()

    assert report.discarded_update_count == 2
    assert report.applied_update_count == 1
    snapshots.snapshot.assert_awaited_once()


async def test_capture_interval_controls_how_many_depth_rows_are_kept():
    """一秒摘要一次，時鐘每次走 0.4 秒，所以不是每筆更新都留一列。"""
    updates = [update(101 + index * 2, 102 + index * 2) for index in range(30)]
    application, _, _, depth_repository = build(
        updates=updates,
        events=[],
        configuration=RecordingConfiguration(
            listing=LISTING, capture_interval_seconds=1.0, duration_seconds=5.0
        ),
    )

    report = await application.run()

    assert report.applied_update_count == 30
    assert 10 <= report.recorded_depth_row_count <= 15
    saved: DepthSeries = depth_repository.save.await_args.args[0]
    assert saved.spread().eq(2.0).all()


async def test_flush_row_count_splits_the_writes():
    application, _, trade_repository, _ = build(
        updates=[],
        events=[trade_event(index) for index in range(10)],
        configuration=RecordingConfiguration(
            listing=LISTING, flush_row_count=4, duration_seconds=5.0
        ),
    )

    report = await application.run()

    assert report.recorded_trade_count == 10
    assert trade_repository.save.await_count == 3  # 4 + 4 + 2
    written: TradeSeries = trade_repository.save.await_args.args[0]
    assert len(written) == 2


async def test_a_slow_stream_still_flushes_on_the_interval():
    """冷清時段湊不滿一批，也不能一直放在記憶體裡。

    時鐘每次走 0.4 秒、間隔設 1 秒，所以每兩三筆成交就會因為「太久沒倒」而寫一次。
    只有列數條件的話，這十筆會全部積著等到錄製結束——中間掉了就是掉了，
    串流沒有重放。
    """
    application, _, trade_repository, _ = build(
        updates=[],
        events=[trade_event(index) for index in range(10)],
        configuration=RecordingConfiguration(
            listing=LISTING,
            flush_row_count=1_000,
            flush_interval_seconds=1.0,
            duration_seconds=5.0,
        ),
    )

    report = await application.run()

    assert report.recorded_trade_count == 10
    assert trade_repository.save.await_count > 1


async def test_trade_rows_carry_the_websocket_source_tag():
    application, _, trade_repository, _ = build(
        updates=[], events=[trade_event(1), trade_event(2)]
    )

    await application.run()

    assert trade_repository.save.await_args.kwargs["source"] == "binance_websocket"


def test_configuration_rejects_a_non_positive_capture_interval():
    with pytest.raises(ValueError):
        RecordingConfiguration(listing=LISTING, capture_interval_seconds=0.0)
