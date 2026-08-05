import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.features.order_book_imbalance import OrderBookImbalance
from quantbot.domain.values.depth_aggregation import DepthAggregation
from quantbot.domain.values.depth_columns import DepthColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
START = "2026-08-04T16:00:00Z"


def make_depth(bid_quantities: list[float], ask_quantities: list[float]) -> DepthSeries:
    """每秒一筆的深度摘要。三個深度都填一樣的值，方便單獨驗某一個。"""
    index = pd.DatetimeIndex(
        pd.date_range(START, periods=len(bid_quantities), freq="1s"),
        name=DepthColumns.CAPTURED_AT,
    )
    frame = pd.DataFrame(
        {"best_bid_price": 63_000.0, "best_ask_price": 63_000.01}, index=index
    )
    for level in DepthColumns.LEVELS:
        frame[DepthColumns.bid_quantity(level)] = bid_quantities
        frame[DepthColumns.ask_quantity(level)] = ask_quantities
    return DepthSeries(LISTING, frame)


def make_candles(bar_count: int) -> CandleSeries:
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


@pytest.mark.parametrize(
    ("bid", "ask", "expected"),
    [
        (1.0, 1.0, 0.0),  # 兩側一樣多
        (3.0, 1.0, 0.5),  # 買方三倍
        (1.0, 3.0, -0.5),
        (1.0, 0.0, 1.0),  # 賣方一張都沒有
        (0.0, 1.0, -1.0),
    ],
)
def test_ratio_is_bounded_and_signed(bid, ask, expected):
    depth = make_depth([bid], [ask])
    assert OrderBookImbalance(5).ratio(depth.frame).iloc[0] == pytest.approx(expected)


def test_both_sides_empty_is_undefined_not_zero():
    """兩側都沒有掛單時 OBI 沒有定義。補 0 會被讀成「兩側一樣多」。"""
    ratio = OrderBookImbalance(5).ratio(make_depth([0.0], [0.0]).frame)

    assert ratio.isna().all()


def test_ratio_is_scale_invariant():
    """除以總量的理由：同樣的失衡在大小市場都得到同一個數字。"""
    small = OrderBookImbalance(5).ratio(make_depth([3.0], [1.0]).frame)
    large = OrderBookImbalance(5).ratio(make_depth([3_000.0], [1_000.0]).frame)

    assert small.iloc[0] == pytest.approx(large.iloc[0])


def test_depth_level_must_have_been_recorded():
    """沒錄的深度算不出來，而且是重錄才救得回來，所以建構時就擋掉。"""
    with pytest.raises(ValueError, match="重新錄"):
        OrderBookImbalance(7)


def test_name_carries_level_and_aggregation():
    assert OrderBookImbalance(10, aggregation=DepthAggregation.LAST).name == (
        "obi_10_last"
    )
    assert OrderBookImbalance(20).name == "obi_20_mean"
    # 原始取樣那一層沒有聚合，名字也不該帶
    assert str(OrderBookImbalance(20).ratio(make_depth([1.0], [1.0]).frame).name) == (
        "obi_20"
    )


def test_feature_contract():
    feature = OrderBookImbalance(5)

    assert feature.warmup_bar_count == 0
    assert feature.required_inputs == frozenset(
        {MarketInput.CANDLES, MarketInput.DEPTH}
    )


def test_compute_aligns_to_the_candle_index():
    """輸出的 index 必須跟 K 線一模一樣，長度也一樣。"""
    view = MarketView(candles=make_candles(3), depth=make_depth([1.0] * 90, [1.0] * 90))

    values = OrderBookImbalance(5).compute(view)

    assert values.index.equals(view.candles.frame.index)
    assert len(values) == 3
    assert values.name == "obi_5_mean"


def test_bars_without_depth_samples_are_nan():
    """掛單簿只有錄製那段時間有資料，K 線有完整歷史。缺的那幾根是 NaN。"""
    view = MarketView(candles=make_candles(5), depth=make_depth([1.0] * 60, [3.0] * 60))

    values = OrderBookImbalance(5).compute(view)

    assert values.iloc[0] == pytest.approx(-0.5)
    assert values.iloc[1:].isna().all()


def test_mean_and_last_disagree_and_both_are_defensible():
    """一分鐘裡壓力翻面的話，平均與收盤取樣會給出相反的答案。"""
    bid = [1.0] * 30 + [9.0] * 30
    ask = [9.0] * 30 + [1.0] * 30
    view = MarketView(candles=make_candles(1), depth=make_depth(bid, ask))

    averaged = OrderBookImbalance(5, aggregation=DepthAggregation.MEAN).compute(view)
    latest = OrderBookImbalance(5, aggregation=DepthAggregation.LAST).compute(view)

    assert averaged.iloc[0] == pytest.approx(0.0)  # 前後抵銷
    assert latest.iloc[0] == pytest.approx(0.8)  # 只看最後一秒


def test_ratio_of_means_is_not_the_mean_of_ratios():
    """順序寫反不會報錯，也照樣落在 −1 到 +1，只有並排對數字才看得出來。

    這一根裡：前 30 秒買 1 賣 9（OBI = −0.8），後 30 秒買 90 賣 10（OBI = +0.8）。
    比例的平均是 0；先把掛量平均起來（買 45.5、賣 9.5）再算比例是 +0.654。
    """
    bid = [1.0] * 30 + [90.0] * 30
    ask = [9.0] * 30 + [10.0] * 30
    depth = make_depth(bid, ask)
    feature = OrderBookImbalance(5)
    view = MarketView(candles=make_candles(1), depth=depth)

    mean_of_ratios = feature.compute(view).iloc[0]

    averaged_bid = depth.frame[DepthColumns.bid_quantity(5)].mean()
    averaged_ask = depth.frame[DepthColumns.ask_quantity(5)].mean()
    ratio_of_means = (averaged_bid - averaged_ask) / (averaged_bid + averaged_ask)

    assert mean_of_ratios == pytest.approx(0.0)
    assert ratio_of_means == pytest.approx(0.654, abs=1e-3)


def test_deeper_levels_can_disagree_with_shallower_ones():
    """前 5 檔與前 20 檔測的是不同的東西，所以它們是兩個特徵而不是一個參數。"""
    index = pd.DatetimeIndex(
        pd.date_range(START, periods=1, freq="1s"), name=DepthColumns.CAPTURED_AT
    )
    frame = pd.DataFrame(
        {
            "best_bid_price": 63_000.0,
            "best_ask_price": 63_000.01,
            DepthColumns.bid_quantity(5): 9.0,
            DepthColumns.ask_quantity(5): 1.0,
            DepthColumns.bid_quantity(10): 9.5,
            DepthColumns.ask_quantity(10): 5.0,
            # 深一點之後賣方壓力反而更大
            DepthColumns.bid_quantity(20): 10.0,
            DepthColumns.ask_quantity(20): 40.0,
        },
        index=index,
    )
    depth = DepthSeries(LISTING, frame)

    assert OrderBookImbalance(5).ratio(depth.frame).iloc[0] == pytest.approx(0.8)
    assert OrderBookImbalance(20).ratio(depth.frame).iloc[0] == pytest.approx(-0.6)


def test_missing_depth_raises_instead_of_returning_nan():
    view = MarketView(candles=make_candles(3))

    assert view.missing_inputs(OrderBookImbalance(5).required_inputs) == frozenset(
        {MarketInput.DEPTH}
    )
    with pytest.raises(ValueError, match="掛單簿"):
        OrderBookImbalance(5).compute(view)


def test_available_inputs_ignores_empty_series():
    """空的 DepthSeries 不算「有掛單簿」。"""
    view = MarketView(candles=make_candles(1), depth=DepthSeries.empty(LISTING))

    assert view.available_inputs() == frozenset({MarketInput.CANDLES})


def test_ratio_matches_a_hand_written_formula_on_random_data():
    generator = np.random.default_rng(20260924)
    bid = generator.uniform(0.01, 50.0, 500).tolist()
    ask = generator.uniform(0.01, 50.0, 500).tolist()
    depth = make_depth(bid, ask)

    expected = (np.array(bid) - np.array(ask)) / (np.array(bid) + np.array(ask))

    assert np.allclose(OrderBookImbalance(10).ratio(depth.frame).to_numpy(), expected)
