import pandas as pd
import pytest

from quantbot.domain.entities.order_book import OrderBook
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.order_book_snapshot import OrderBookSnapshot
from quantbot.domain.values.order_book_update import OrderBookUpdate
from quantbot.domain.values.price_level import PriceLevel

CAPTURED_AT = pd.Timestamp("2026-07-15T00:00:00Z")


def snapshot(last_update_id: int = 100) -> OrderBookSnapshot:
    """六檔對稱的簿子：買方 99 往下、賣方 101 往上，每檔各 1.0。"""
    return OrderBookSnapshot(
        last_update_id=last_update_id,
        bids=tuple(PriceLevel(99.0 - index, 1.0) for index in range(30)),
        asks=tuple(PriceLevel(101.0 + index, 1.0) for index in range(30)),
    )


def test_snapshot_defines_the_starting_state():
    book = OrderBook(snapshot())

    assert book.last_update_id == 100
    assert book.best_bid_price == 99.0
    assert book.best_ask_price == 101.0
    assert len(book) == 60


def test_update_replaces_quantity_and_advances_the_sequence():
    book = OrderBook(snapshot())

    book.apply(
        OrderBookUpdate(
            event_time=CAPTURED_AT,
            first_update_id=101,
            final_update_id=104,
            bid_changes=(PriceLevel(99.0, 5.0),),
            ask_changes=(PriceLevel(101.0, 7.0),),
        )
    )

    summary = book.summarize(CAPTURED_AT)
    assert book.last_update_id == 104
    assert summary.depth_quantities[0].bid_quantity == pytest.approx(5.0 + 4.0)
    assert summary.depth_quantities[0].ask_quantity == pytest.approx(7.0 + 4.0)


def test_zero_quantity_removes_the_level_instead_of_keeping_a_zero():
    """掛量 0 是「這一檔清空了」。留著它的症狀是前 N 檔實際上只涵蓋 N-1 檔。"""
    book = OrderBook(snapshot())

    book.apply(
        OrderBookUpdate(
            event_time=CAPTURED_AT,
            first_update_id=101,
            final_update_id=101,
            bid_changes=(PriceLevel(99.0, 0.0),),
            ask_changes=(),
        )
    )

    assert book.best_bid_price == 98.0
    assert len(book) == 59
    # 前五檔仍然是五檔真實掛單，不是四檔加一個 0
    assert book.summarize(CAPTURED_AT).depth_quantities[
        0
    ].bid_quantity == pytest.approx(5.0)


def test_update_can_add_a_level_outside_the_snapshot():
    """增量更新會帶來快照範圍外的新價位，簿子要接受它。"""
    book = OrderBook(snapshot())

    book.apply(
        OrderBookUpdate(
            event_time=CAPTURED_AT,
            first_update_id=101,
            final_update_id=101,
            bid_changes=(PriceLevel(99.5, 2.0),),
            ask_changes=(),
        )
    )

    assert book.best_bid_price == 99.5
    assert len(book) == 61


def test_summary_uses_opposite_orderings_for_the_two_sides():
    """買方要價格最高的前 N 檔，賣方要價格最低的前 N 檔。

    兩邊都用同一個方向排序的話，數值範圍看起來完全正常，但掛單不對稱的
    正負號會整批顛倒——這是這個 entity 最需要被釘住的一件事。
    """
    book = OrderBook(
        OrderBookSnapshot(
            last_update_id=1,
            # 買方最好的那一檔（100）掛得特別多
            bids=(PriceLevel(100.0, 9.0), PriceLevel(99.0, 1.0), PriceLevel(98.0, 1.0)),
            # 賣方最好的那一檔（101）掛得特別少
            asks=(
                PriceLevel(101.0, 1.0),
                PriceLevel(102.0, 9.0),
                PriceLevel(103.0, 9.0),
            ),
        )
    )

    quantities = book.summarize(CAPTURED_AT).depth_quantities[0]
    assert quantities.level == DepthColumns.LEVELS[0]
    assert quantities.bid_quantity == pytest.approx(11.0)
    assert quantities.ask_quantity == pytest.approx(19.0)


def test_summary_row_matches_the_column_vocabulary():
    row = OrderBook(snapshot()).summarize(CAPTURED_AT).as_row()

    assert set(row) == set(DepthColumns.all_columns())


def test_spread_and_mid_price():
    summary = OrderBook(snapshot()).summarize(CAPTURED_AT)

    assert summary.spread == pytest.approx(2.0)
    assert summary.mid_price == pytest.approx(100.0)


def test_empty_side_does_not_raise():
    """交易所維護或極端行情下，某一側真的可能空掉。回 NaN 而不是丟例外。"""
    book = OrderBook(OrderBookSnapshot(last_update_id=1, bids=(), asks=()))

    assert pd.isna(book.best_bid_price)
    assert pd.isna(book.summarize(CAPTURED_AT).spread)
