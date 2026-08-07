import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.services.volume_profile_service import VolumeProfileService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.trade_columns import TradeColumns
from quantbot.domain.values.volume_profile import VolumeProfile

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)


def make_trades(prices, quantities) -> TradeSeries:
    count = len(prices)
    index = pd.DatetimeIndex(
        pd.date_range("2026-07-15", periods=count, freq="1s"),
        name=TradeColumns.TRANSACT_TIME,
    )
    trade_ids = np.arange(1, count + 1)
    return TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: trade_ids,
                TradeColumns.FIRST_TRADE_ID: trade_ids,
                TradeColumns.LAST_TRADE_ID: trade_ids,
                TradeColumns.PRICE: prices,
                TradeColumns.QUANTITY: quantities,
                TradeColumns.BUYER_IS_MAKER: [False] * count,
            },
            index=index,
        ),
    )


def make_candles(highs, lows, closes, volumes) -> CandleSeries:
    index = pd.date_range(
        "2026-07-15", periods=len(closes), freq="1min", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            },
            index=index,
        ),
    )


def profile_of(volumes: list[float], prices: list[float]) -> VolumeProfile:
    return VolumeProfile(
        volume_by_price=pd.Series(volumes, index=prices, name="volume"),
        value_area_fraction=0.7,
    )


def test_point_of_control_is_the_busiest_price():
    profile = profile_of([1.0, 9.0, 2.0], [100.0, 101.0, 102.0])

    assert profile.point_of_control == pytest.approx(101.0)
    assert profile.total_volume == pytest.approx(12.0)


def test_value_area_expands_from_the_peak_towards_the_larger_neighbour():
    """貪婪擴張：每一步選相鄰兩側裡成交量較大的那一格。

    這裡 POC 在 102（成交 10）。左邊是 4、右邊是 3，所以先往左；
    累積 14 已經超過 20 × 0.7 = 14，停下來。結果是不對稱的區間。
    """
    profile = VolumeProfile(
        volume_by_price=pd.Series(
            [1.0, 2.0, 4.0, 10.0, 3.0], index=[99.0, 100.0, 101.0, 102.0, 103.0]
        ),
        value_area_fraction=0.7,
    )

    low, high = profile.value_area

    assert profile.point_of_control == pytest.approx(102.0)
    assert (low, high) == (pytest.approx(101.0), pytest.approx(102.0))


def test_value_area_covers_at_least_the_requested_fraction():
    generator = np.random.default_rng(20260928)
    volumes = generator.uniform(0.1, 10.0, 60)
    prices = np.linspace(64_000, 65_000, 60)
    profile = VolumeProfile(
        volume_by_price=pd.Series(volumes, index=prices), value_area_fraction=0.7
    )

    low, high = profile.value_area
    inside = (prices >= low) & (prices <= high)

    assert volumes[inside].sum() >= profile.total_volume * 0.7


def test_value_area_of_the_whole_range_is_the_whole_range():
    profile = profile_of([1.0, 2.0, 3.0], [100.0, 101.0, 102.0])
    whole = VolumeProfile(
        volume_by_price=profile.volume_by_price, value_area_fraction=1.0
    )

    assert whole.value_area == (pytest.approx(100.0), pytest.approx(102.0))


def test_rejects_an_impossible_value_area_fraction():
    with pytest.raises(ValueError):
        profile_of([1.0], [100.0]).__class__(
            volume_by_price=pd.Series([1.0], index=[100.0]), value_area_fraction=0.0
        )


def test_from_trades_puts_every_trade_in_its_own_price_bucket():
    """精算路徑不需要任何假設：每一筆成交都知道自己的價格。"""
    trades = make_trades(
        prices=[100.0, 100.0, 110.0, 120.0], quantities=[3.0, 4.0, 1.0, 2.0]
    )

    profile = VolumeProfileService(bucket_count=3).from_trades(trades)

    assert profile.total_volume == pytest.approx(10.0)
    assert profile.point_of_control == pytest.approx(103.33, abs=0.01)


def test_a_single_price_degenerates_to_one_bucket():
    """整段只有一個成交價時硬分桶會讓邊界重疊。"""
    trades = make_trades(prices=[100.0, 100.0], quantities=[1.0, 2.0])

    profile = VolumeProfileService(bucket_count=50).from_trades(trades)

    assert len(profile.volume_by_price) == 1
    assert profile.point_of_control == pytest.approx(100.0)
    assert profile.total_volume == pytest.approx(3.0)


def test_candle_approximation_puts_the_whole_bar_on_one_price():
    """近似法把整根的量塞在典型價上，於是分布出現實際上不存在的尖峰。"""
    candles = make_candles(highs=[110.0], lows=[90.0], closes=[100.0], volumes=[10.0])

    profile = VolumeProfileService(bucket_count=5).from_candles(candles)

    # 只有一根 K 線，所以典型價只有一個值，退化成單一桶
    assert len(profile.volume_by_price) == 1
    assert profile.point_of_control == pytest.approx(100.0)  # (110 + 90 + 100) / 3


def test_the_two_paths_disagree_on_where_the_volume_sits():
    """同一段行情，精算與近似算出來的 POC 不一樣——這是這一天的重點。

    逐筆成交：大部分的量成交在 90 附近。
    K 線近似：那一根的典型價是 100，於是整份量被記在 100。
    """
    trades = make_trades(prices=[90.0] * 9 + [110.0], quantities=[1.0] * 9 + [1.0])
    candles = make_candles(highs=[110.0], lows=[90.0], closes=[100.0], volumes=[10.0])
    service = VolumeProfileService(bucket_count=5)

    exact = service.from_trades(trades)
    approximate = service.from_candles(candles)

    assert exact.total_volume == pytest.approx(approximate.total_volume)
    assert exact.point_of_control == pytest.approx(92.0)
    assert approximate.point_of_control == pytest.approx(100.0)


def test_empty_input_raises_instead_of_returning_an_empty_profile():
    with pytest.raises(ValueError, match="沒有資料"):
        VolumeProfileService().from_trades(TradeSeries.empty(LISTING))


def test_rejects_too_few_buckets():
    with pytest.raises(ValueError):
        VolumeProfileService(bucket_count=1)
