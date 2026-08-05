import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.features.liquidity_swing import LiquiditySwing
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.extreme_side import ExtremeSide
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.trade_columns import TradeColumns

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
START = pd.Timestamp("2026-08-04T17:20:00Z")


def make_depth(ask_quantities: list[float], bid_quantities: list[float]) -> DepthSeries:
    index = pd.DatetimeIndex(
        [START + pd.Timedelta(seconds=index) for index in range(len(ask_quantities))],
        name=DepthColumns.CAPTURED_AT,
    )
    frame = pd.DataFrame(
        {"best_bid_price": 63_000.0, "best_ask_price": 63_000.01}, index=index
    )
    for level in DepthColumns.LEVELS:
        frame[DepthColumns.ask_quantity(level)] = ask_quantities
        frame[DepthColumns.bid_quantity(level)] = bid_quantities
    return DepthSeries(LISTING, frame)


def make_trades(
    offsets_seconds: list[float],
    quantities: list[float],
    buyer_is_maker: list[bool],
) -> TradeSeries:
    index = pd.DatetimeIndex(
        [START + pd.Timedelta(seconds=offset) for offset in offsets_seconds],
        name=TradeColumns.TRANSACT_TIME,
    )
    trade_ids = np.arange(1, len(quantities) + 1)
    return TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: trade_ids,
                TradeColumns.FIRST_TRADE_ID: trade_ids,
                TradeColumns.LAST_TRADE_ID: trade_ids,
                TradeColumns.PRICE: 63_000.0,
                TradeColumns.QUANTITY: quantities,
                TradeColumns.BUYER_IS_MAKER: buyer_is_maker,
            },
            index=index,
        ),
    )


def make_candles(bar_count: int = 1) -> CandleSeries:
    index = pd.date_range(
        START, periods=bar_count, freq="1min", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": 63_000.0,
                "high": 63_010.0,
                "low": 62_990.0,
                "close": 63_005.0,
                "volume": 1.0,
            },
            index=index,
        ),
    )


def test_depth_eaten_by_trades_gives_a_ratio_near_one():
    """賣方深度掉了 5 BTC，同期間有 5 BTC 的主動買。那是被吃掉的。"""
    depth = make_depth(ask_quantities=[10.0, 5.0], bid_quantities=[10.0, 10.0])
    trades = make_trades([1.0], [5.0], [False])  # 主動買
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    ratio = LiquiditySwing(side=ExtremeSide.HIGH).consumed_ratio(view)

    assert ratio.iloc[1] == pytest.approx(1.0)


def test_depth_that_vanishes_without_trades_gives_a_ratio_near_zero():
    """賣方深度掉了 5 BTC，但完全沒有成交。那是被撤走的。"""
    depth = make_depth(ask_quantities=[10.0, 5.0], bid_quantities=[10.0, 10.0])
    trades = make_trades([1.0], [0.001], [False])
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    ratio = LiquiditySwing(side=ExtremeSide.HIGH).consumed_ratio(view)

    assert ratio.iloc[1] < 0.01


def test_duplicate_trade_timestamps_do_not_break_the_alignment():
    """成交的時間戳不是唯一的，而 reindex 在重複索引上會直接丟 ValueError。

    這是實跑撞到的：同一個毫秒裡有幾十筆成交是常態。這個測試把它釘住，
    因為那個例外只在真實資料上才出現，合成的「每秒一筆」測不到。
    """
    depth = make_depth(ask_quantities=[10.0, 4.0], bid_quantities=[10.0, 10.0])
    # 六筆成交全部落在同一個時間點
    trades = make_trades([1.0] * 6, [1.0] * 6, [False] * 6)
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    ratio = LiquiditySwing(side=ExtremeSide.HIGH).consumed_ratio(view)

    assert ratio.iloc[1] == pytest.approx(1.0)  # 6 BTC 的買，吃掉 6 BTC 的深度


def test_the_two_sides_look_at_opposite_depths():
    """往上突破要吃賣單，往下要吃買單。對應寫反的話比例還是合理，只是無關。"""
    depth = make_depth(ask_quantities=[10.0, 10.0], bid_quantities=[10.0, 2.0])
    trades = make_trades([1.0], [8.0], [True])  # 主動賣
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    assert LiquiditySwing(side=ExtremeSide.LOW).consumed_ratio(view).iloc[
        1
    ] == pytest.approx(1.0)
    # 賣方深度沒有減少，所以往上那一側沒有定義
    assert pd.isna(LiquiditySwing(side=ExtremeSide.HIGH).consumed_ratio(view).iloc[1])


def test_ratio_above_one_is_kept_not_clipped():
    """有人一邊吃、一邊有新單補上時，比例會大於 1。那是資訊，不是錯誤。"""
    depth = make_depth(ask_quantities=[10.0, 9.0], bid_quantities=[10.0, 10.0])
    trades = make_trades([1.0], [5.0], [False])
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    assert LiquiditySwing(side=ExtremeSide.HIGH).consumed_ratio(view).iloc[1] > 1.0


def test_requires_all_three_inputs():
    feature = LiquiditySwing(side=ExtremeSide.HIGH)

    assert feature.required_inputs == frozenset(
        {MarketInput.CANDLES, MarketInput.TRADES, MarketInput.DEPTH}
    )
    with pytest.raises(ValueError, match="逐筆成交"):
        feature.compute(
            MarketView(candles=make_candles(), depth=make_depth([1.0], [1.0]))
        )


def test_compute_aligns_to_the_candle_index():
    depth = make_depth(
        ask_quantities=[10.0 - index * 0.1 for index in range(60)],
        bid_quantities=[10.0] * 60,
    )
    trades = make_trades(
        [float(index) for index in range(60)], [0.05] * 60, [False] * 60
    )
    view = MarketView(candles=make_candles(), trades=trades, depth=depth)

    values = LiquiditySwing(side=ExtremeSide.HIGH).compute(view)

    assert values.index.equals(view.candles.frame.index)
    assert values.notna().all()


def test_rejects_a_non_positive_window():
    with pytest.raises(ValueError):
        LiquiditySwing(side=ExtremeSide.HIGH, window_seconds=0.0)
