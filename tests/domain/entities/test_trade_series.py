import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.trade_columns import TradeColumns

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)


def make_series(
    *,
    prices: list[float],
    quantities: list[float] | None = None,
    buyer_is_maker: list[bool] | None = None,
    start: str = "2026-07-15T00:00:00Z",
    step_seconds: float = 10.0,
    first_trade_id: int = 1_000,
) -> TradeSeries:
    count = len(prices)
    index = pd.DatetimeIndex(
        pd.Timestamp(start)
        + pd.to_timedelta(np.arange(count) * step_seconds, unit="s"),
        name=TradeColumns.TRANSACT_TIME,
    )
    trade_ids = np.arange(first_trade_id, first_trade_id + count)
    return TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: trade_ids,
                TradeColumns.FIRST_TRADE_ID: trade_ids,
                TradeColumns.LAST_TRADE_ID: trade_ids,
                TradeColumns.PRICE: prices,
                TradeColumns.QUANTITY: quantities or [1.0] * count,
                TradeColumns.BUYER_IS_MAKER: buyer_is_maker or [False] * count,
            },
            index=index,
        ),
    )


def test_merge_deduplicates_by_trade_id_not_by_timestamp():
    """同一個時間戳可以有很多筆成交，所以去重 NEVER 看索引。"""
    same_moment = pd.DatetimeIndex(
        [pd.Timestamp("2026-07-15T00:00:00Z")] * 3, name=TradeColumns.TRANSACT_TIME
    )
    frame = pd.DataFrame(
        {
            TradeColumns.TRADE_ID: [1, 2, 3],
            TradeColumns.FIRST_TRADE_ID: [1, 2, 3],
            TradeColumns.LAST_TRADE_ID: [1, 2, 3],
            TradeColumns.PRICE: [100.0, 100.5, 101.0],
            TradeColumns.QUANTITY: [1.0, 2.0, 3.0],
            TradeColumns.BUYER_IS_MAKER: [False, True, False],
        },
        index=same_moment,
    )
    series = TradeSeries(LISTING, frame)

    merged = series.merge(series)

    assert len(series) == 3  # 三筆同時間的成交都留著
    assert len(merged) == 3  # 併自己不會變成六筆
    assert merged.frame[TradeColumns.QUANTITY].sum() == pytest.approx(6.0)


def test_merge_prefers_self_on_overlap():
    archive = make_series(prices=[100.0, 101.0], quantities=[1.0, 1.0])
    stream = make_series(prices=[999.0, 999.0], quantities=[5.0, 5.0])

    merged = archive.merge(stream)

    assert merged.frame[TradeColumns.PRICE].tolist() == [100.0, 101.0]


def test_merge_rejects_a_different_listing():
    other = TradeSeries.empty(Listing(symbol="ETH/USDT", market=Market.SPOT))
    with pytest.raises(ValueError):
        make_series(prices=[100.0]).merge(other)


def test_restricted_to_is_half_open():
    series = make_series(prices=[100.0] * 6, step_seconds=60.0)
    period = TimeRange(
        pd.Timestamp("2026-07-15T00:01:00Z"), pd.Timestamp("2026-07-15T00:03:00Z")
    )

    restricted = series.restricted_to(period)

    assert len(restricted) == 2
    assert restricted.transact_times[0] == pd.Timestamp("2026-07-15T00:01:00Z")


def test_missing_trade_id_count_finds_the_break():
    """斷號 NEVER 以缺列的形式出現：表看起來連續，只是少了幾筆成交。"""
    index = pd.DatetimeIndex(
        pd.date_range("2026-07-15", periods=3, freq="1s"),
        name=TradeColumns.TRANSACT_TIME,
    )
    series = TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: [1, 2, 3],
                TradeColumns.FIRST_TRADE_ID: [10, 20, 31],
                TradeColumns.LAST_TRADE_ID: [19, 25, 40],  # 26-30 沒有被涵蓋
                TradeColumns.PRICE: [100.0, 100.0, 100.0],
                TradeColumns.QUANTITY: [1.0, 1.0, 1.0],
                TradeColumns.BUYER_IS_MAKER: [False, False, False],
            },
            index=index,
        ),
    )

    assert series.missing_trade_id_count() == 5


def test_no_break_in_a_continuous_series():
    assert make_series(prices=[100.0] * 10).missing_trade_id_count() == 0


def test_empty_series_has_the_right_dtypes():
    empty = TradeSeries.empty(LISTING)

    assert empty.is_empty()
    assert empty.missing_trade_id_count() == 0
    assert list(empty.frame.columns) == list(TradeColumns.all_columns())


def test_aggregate_to_candles_rebuilds_every_column():
    """把六筆成交聚合成一根 1 分鐘 K 線，九個欄位逐一手算對照。"""
    series = make_series(
        prices=[100.0, 105.0, 95.0, 102.0, 101.0, 103.0],
        quantities=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        # 主動買：第 1、3、5 筆（buyer_is_maker=False）
        buyer_is_maker=[False, True, False, True, False, True],
        step_seconds=5.0,
    )

    candles = series.aggregate_to_candles(Timeframe("1m")).frame
    bar = candles.iloc[0]

    assert len(candles) == 1
    assert bar["open"] == pytest.approx(100.0)
    assert bar["high"] == pytest.approx(105.0)
    assert bar["low"] == pytest.approx(95.0)
    assert bar["close"] == pytest.approx(103.0)
    assert bar["volume"] == pytest.approx(21.0)
    assert bar["quote_volume"] == pytest.approx(
        100.0 * 1 + 105.0 * 2 + 95.0 * 3 + 102.0 * 4 + 101.0 * 5 + 103.0 * 6
    )
    assert bar["taker_buy_base_volume"] == pytest.approx(1.0 + 3.0 + 5.0)
    assert bar["taker_buy_quote_volume"] == pytest.approx(
        100.0 * 1 + 95.0 * 3 + 101.0 * 5
    )
    assert bar["trade_count"] == 6


def test_aggregate_to_candles_counts_merged_trades_not_rows():
    """aggTrades 的一列可能併了很多筆成交，trade_count 要看 last - first + 1。"""
    index = pd.DatetimeIndex(
        [pd.Timestamp("2026-07-15T00:00:00Z")], name=TradeColumns.TRANSACT_TIME
    )
    series = TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: [1],
                TradeColumns.FIRST_TRADE_ID: [100],
                TradeColumns.LAST_TRADE_ID: [142],  # 一列 = 43 筆成交
                TradeColumns.PRICE: [100.0],
                TradeColumns.QUANTITY: [7.0],
                TradeColumns.BUYER_IS_MAKER: [False],
            },
            index=index,
        ),
    )

    candles = series.aggregate_to_candles(Timeframe("1m")).frame

    assert candles.iloc[0]["trade_count"] == 43


def test_aggregate_to_candles_skips_minutes_without_trades():
    """完全沒成交的那一分鐘官方也不出 K 線，補一根假的等於捏造資料。"""
    series = make_series(prices=[100.0, 101.0], step_seconds=180.0)

    candles = series.aggregate_to_candles(Timeframe("1m"))

    assert len(candles) == 2  # 中間那兩分鐘沒有 K 線
    assert candles.instrument.timeframe == Timeframe("1m")
    assert candles.instrument.symbol == LISTING.symbol


def test_taker_sides_maps_buyer_is_maker_to_the_active_side():
    series = make_series(prices=[100.0, 100.0], buyer_is_maker=[True, False])

    assert series.taker_sides().tolist() == ["sell", "buy"]
