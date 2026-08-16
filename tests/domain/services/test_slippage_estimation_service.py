import pandas as pd
import pytest

from quantbot.domain.entities.depth_series import DepthSeries
from quantbot.domain.services.slippage_estimation_service import (
    SlippageEstimationService,
)
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)


def make_depth(
    bids: list[float], asks: list[float], quantities: list[float] | None = None
) -> DepthSeries:
    index = pd.date_range("2026-08-04 16:00", periods=len(bids), freq="1s", tz="UTC")
    sizes = quantities if quantities is not None else [1.0] * len(bids)
    return DepthSeries(
        LISTING,
        pd.DataFrame(
            {
                "best_bid_price": bids,
                "best_ask_price": asks,
                "bid_quantity_5": sizes,
                "ask_quantity_5": sizes,
                "bid_quantity_10": sizes,
                "ask_quantity_10": sizes,
                "bid_quantity_20": sizes,
                "ask_quantity_20": sizes,
            },
            index=index,
        ),
    )


def test_half_the_spread_relative_to_the_mid_price():
    # 價差 2、中間價 100，所以半價差是 1%
    depth = make_depth([99.0, 99.0], [101.0, 101.0])

    estimate = SlippageEstimationService().estimate(depth, order_notional=1_000.0)

    assert estimate.median_half_spread_rate == pytest.approx(0.01)
    assert estimate.mean_half_spread_rate == pytest.approx(0.01)
    assert estimate.sample_count == 2


def test_the_suggested_rate_is_the_95th_percentile_not_the_median():
    """訊號常出現在波動放大的時候，而價差跟波動同向，用中位數會系統性低估。"""
    bids = [99.9] * 95 + [99.0] * 5
    asks = [100.1] * 95 + [101.0] * 5
    depth = make_depth(bids, asks)

    estimate = SlippageEstimationService().estimate(depth, order_notional=1_000.0)

    assert estimate.suggested_slippage_rate > estimate.median_half_spread_rate
    assert estimate.suggested_slippage_rate == pytest.approx(
        estimate.percentile95_half_spread_rate
    )


def test_the_order_size_is_compared_against_the_top_five_levels():
    depth = make_depth([99.0] * 3, [101.0] * 3, quantities=[2.0] * 3)

    small = SlippageEstimationService().estimate(depth, order_notional=100.0)
    large = SlippageEstimationService().estimate(depth, order_notional=1_000.0)

    # 前五檔買方名目 = 2 顆 × 中間價 100 = 200
    assert small.median_top_5_notional == pytest.approx(200.0)
    assert small.order_fits_in_top_5
    assert not large.order_fits_in_top_5


def test_covered_hours_uses_the_span_not_the_sample_count():
    """錄製中斷過的話，樣本數除以取樣頻率會高估涵蓋範圍。"""
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-08-04 16:00", tz="UTC"),
            pd.Timestamp("2026-08-04 16:01", tz="UTC"),
            pd.Timestamp("2026-08-04 18:00", tz="UTC"),
        ]
    )
    depth = DepthSeries(
        LISTING,
        pd.DataFrame(
            {
                "best_bid_price": [99.0, 99.0, 99.0],
                "best_ask_price": [101.0, 101.0, 101.0],
                "bid_quantity_5": [1.0, 1.0, 1.0],
                "ask_quantity_5": [1.0, 1.0, 1.0],
                "bid_quantity_10": [1.0, 1.0, 1.0],
                "ask_quantity_10": [1.0, 1.0, 1.0],
                "bid_quantity_20": [1.0, 1.0, 1.0],
                "ask_quantity_20": [1.0, 1.0, 1.0],
            },
            index=index,
        ),
    )

    estimate = SlippageEstimationService().estimate(depth, order_notional=100.0)

    assert estimate.sample_count == 3
    assert estimate.covered_hours == pytest.approx(2.0)


def test_an_empty_depth_series_is_an_error_not_a_zero():
    with pytest.raises(ValueError, match="估不出滑價"):
        SlippageEstimationService().estimate(
            DepthSeries.empty(LISTING), order_notional=100.0
        )


def test_a_non_positive_order_notional_is_rejected():
    depth = make_depth([99.0], [101.0])

    with pytest.raises(ValueError, match="order_notional"):
        SlippageEstimationService().estimate(depth, order_notional=0.0)
