# quantbot/application/record_microstructure_application.py
from __future__ import annotations

import asyncio

import pandas as pd

from quantbot.domain.dto.recording_report import RecordingReportDto
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.entities.order_book import OrderBook
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
from quantbot.domain.values.order_book_depth_summary import OrderBookDepthSummary
from quantbot.domain.values.recording_configuration import RecordingConfiguration
from quantbot.domain.values.sequence_decision import SequenceDecision
from quantbot.domain.values.trade_columns import TradeColumns
from quantbot.domain.values.trade_event import TradeEvent


class RecordMicrostructureApplication:
    """把即時的成交與掛單簿錄下來。

    兩條串流同時跑，各自獨立：成交收下來就好，掛單簿要維護狀態。它們用
    asyncio.TaskGroup 一起管——任一條掉了就整組結束，NEVER 留下「成交還在錄、
    掛單簿其實早就斷了」這種半死狀態，那會產出一段看起來完整、其實只有一半的資料。

    這個用例自己不解析任何 JSON、不知道 WebSocket 存在、也不判斷序號接不接受。
    它負責的是三個決定：狀態要不要重建、什麼時候摘要一次、緩衝滿了要不要倒出去。
    """

    def __init__(
        self,
        configuration: RecordingConfiguration,
        *,
        trades: TradeStream,
        order_book: OrderBookStream,
        snapshots: OrderBookSnapshotSource,
        trade_repository: TradeRepository,
        depth_repository: DepthRepository,
        sequence: OrderBookSequenceService,
        clock: Clock,
    ) -> None:
        self._configuration = configuration
        self._trades = trades
        self._order_book = order_book
        self._snapshots = snapshots
        self._trade_repository = trade_repository
        self._depth_repository = depth_repository
        self._sequence = sequence
        self._clock = clock

        self._trade_buffer: list[TradeEvent] = []
        self._depth_buffer: list[OrderBookDepthSummary] = []
        self._latest_trade_flush_at = clock.now()
        self._latest_depth_flush_at = self._latest_trade_flush_at
        self._recorded_trade_count = 0
        self._recorded_depth_row_count = 0
        self._applied_update_count = 0
        self._discarded_update_count = 0
        self._resynchronization_count = 0

    async def run(self) -> RecordingReportDto:
        """錄到時間到（或串流結束）為止，然後把剩下的緩衝倒完。

        duration_seconds 為 None 就一直跑，所以正式部署不需要外面包一層排程；
        文章與測試給它一個秒數，才有辦法在有限時間內看到結果。
        """
        try:
            async with asyncio.timeout(self._configuration.duration_seconds):
                async with asyncio.TaskGroup() as group:
                    group.create_task(self._consume_trades())
                    group.create_task(self._consume_order_book())
        except TimeoutError:
            pass  # 時間到是正常的結束方式，不是錯誤

        await self._flush_trades()
        await self._flush_depth()
        return RecordingReportDto(
            listing=self._configuration.listing,
            recorded_trade_count=self._recorded_trade_count,
            recorded_depth_row_count=self._recorded_depth_row_count,
            applied_update_count=self._applied_update_count,
            discarded_update_count=self._discarded_update_count,
            resynchronization_count=self._resynchronization_count,
        )

    async def _consume_trades(self) -> None:
        async for event in self._trades.events(self._configuration.listing):
            self._trade_buffer.append(event)
            if self._is_due(len(self._trade_buffer), self._latest_trade_flush_at):
                await self._flush_trades()

    async def _consume_order_book(self) -> None:
        """維護本地簿子，並按固定間隔摘要一次。

        摘要跟套用更新在同一個協程裡，所以 NEVER 會摘到一份「套了一半」的簿子。
        另開一個協程定時摘要看起來更整齊，但那需要在兩者之間加鎖，
        而鎖是為了修補一個不必存在的問題。

        **順序很重要：先訂閱，收到第一筆更新之後才去拉快照。** 反過來寫（先拉快照
        再訂閱）看起來更自然，但那之間有一段空窗——快照拍完、連線還沒建立的那幾百
        毫秒裡發生的變動沒有人收到，所以第一筆更新一定接不上，啟動時必然多一次重拉。
        實測過：先快照後訂閱的版本，每次啟動的 resynchronization_count 都是 1。

        先訂閱的話，拉快照期間的更新會待在 WebSocket 的接收緩衝裡，一筆都不會掉；
        它們的序號比快照舊，於是被 DISCARD 掉，這正是那個計數器該有的用途。
        """
        book: OrderBook | None = None
        next_capture = self._clock.now()
        still_synchronizing = True

        async for update in self._order_book.updates(self._configuration.listing):
            if book is None:
                # 第一筆更新已經在手上（也就是訂閱確實成功了）才拉快照
                book = await self._resynchronize()
            decision = self._sequence.decide(
                book.last_update_id, update, still_synchronizing=still_synchronizing
            )
            if decision is SequenceDecision.DISCARD:
                self._discarded_update_count += 1
                continue
            if decision is SequenceDecision.RESYNCHRONIZE:
                self._resynchronization_count += 1
                book = await self._resynchronize()
                still_synchronizing = True
                continue

            book.apply(update)
            self._applied_update_count += 1
            still_synchronizing = False

            now = self._clock.now()
            if now >= next_capture:
                self._depth_buffer.append(book.summarize(now))
                next_capture = now + self._configuration.capture_interval
                if self._is_due(len(self._depth_buffer), self._latest_depth_flush_at):
                    await self._flush_depth()

    def _is_due(self, buffered_row_count: int, latest_flush_at: pd.Timestamp) -> bool:
        """該倒緩衝了嗎：攢夠一批，或者離上次倒出去已經太久。

        兩個條件都要有。只看列數的話，冷清時段可能幾十分鐘湊不滿一批，而那段時間
        程式一旦掛掉，緩衝裡的東西就跟著沒了——那是唯一一份，串流不能重放。
        """
        if buffered_row_count >= self._configuration.flush_row_count:
            return True
        elapsed_seconds = (self._clock.now() - latest_flush_at).total_seconds()
        return (
            buffered_row_count > 0
            and elapsed_seconds >= self._configuration.flush_interval_seconds
        )

    async def _resynchronize(self) -> OrderBook:
        snapshot = await self._snapshots.snapshot(
            self._configuration.listing, depth=self._configuration.snapshot_depth
        )
        return OrderBook(snapshot)

    async def _flush_trades(self) -> None:
        if not self._trade_buffer:
            return
        series = TradeSeries(
            self._configuration.listing, self._as_frame(self._trade_buffer)
        )
        self._trade_buffer = []
        self._latest_trade_flush_at = self._clock.now()
        self._recorded_trade_count += await self._trade_repository.save(
            series, source="binance_websocket"
        )

    async def _flush_depth(self) -> None:
        if not self._depth_buffer:
            return
        series = DepthSeries.of_summaries(
            self._configuration.listing, self._depth_buffer
        )
        self._depth_buffer = []
        self._latest_depth_flush_at = self._clock.now()
        self._recorded_depth_row_count += await self._depth_repository.save(series)

    @staticmethod
    def _as_frame(events: list[TradeEvent]) -> pd.DataFrame:
        """一次把整個緩衝轉成表，NEVER 一筆一筆寫進資料庫。

        每筆成交一次 INSERT 的話，BTC/USDT 活躍時段一秒幾十筆就會讓連線變成瓶頸，
        而且每一筆都是一次獨立交易。攢一批再 COPY，寫入從瓶頸變成不用管的事。
        """
        index = pd.DatetimeIndex(
            [event.transact_time for event in events], name=TradeColumns.TRANSACT_TIME
        )
        return pd.DataFrame(
            {
                TradeColumns.TRADE_ID: [event.trade_id for event in events],
                TradeColumns.FIRST_TRADE_ID: [event.first_trade_id for event in events],
                TradeColumns.LAST_TRADE_ID: [event.last_trade_id for event in events],
                TradeColumns.PRICE: [event.price for event in events],
                TradeColumns.QUANTITY: [event.quantity for event in events],
                TradeColumns.BUYER_IS_MAKER: [event.buyer_is_maker for event in events],
            },
            index=index,
        )
