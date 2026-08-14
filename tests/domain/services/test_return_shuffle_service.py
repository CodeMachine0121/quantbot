import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.services.return_shuffle_service import ReturnShuffleService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_prices(bar_count: int = 500, seed: int = 5) -> pd.Series:
    generator = np.random.default_rng(seed)
    values = 100.0 * np.exp(np.cumsum(generator.normal(0.0002, 0.012, bar_count)))
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")
    return pd.Series(values, index=index, name="close")


def test_the_distribution_of_returns_is_preserved_exactly():
    """保留分布、只破壞順序，是這個示範公平的前提。"""
    prices = make_prices()

    shuffled = ReturnShuffleService().shuffled_prices(prices, seed=1)

    original_returns = np.diff(np.log(prices.to_numpy()))
    shuffled_returns = np.diff(np.log(shuffled.to_numpy()))
    # 容忍度不是 1e-12：重建價格走的是 exp(cumsum(log 報酬))，
    # 而那一趟來回會累積浮點誤差。這裡要驗的是「同一組報酬換了順序」，不是位元相同
    np.testing.assert_allclose(
        np.sort(original_returns), np.sort(shuffled_returns), rtol=1e-9, atol=1e-15
    )
    assert shuffled_returns.std() == pytest.approx(original_returns.std())


def test_the_order_really_is_different():
    prices = make_prices()

    shuffled = ReturnShuffleService().shuffled_prices(prices, seed=1)

    assert not np.allclose(prices.to_numpy(), shuffled.to_numpy())


def test_the_starting_price_and_the_index_are_untouched():
    prices = make_prices()

    shuffled = ReturnShuffleService().shuffled_prices(prices, seed=1)

    assert shuffled.iloc[0] == pytest.approx(prices.iloc[0])
    assert shuffled.index.equals(prices.index)


def test_the_same_seed_gives_the_same_fake_data():
    """示範要能被重現，所以種子是參數而不是全域狀態。"""
    prices = make_prices()
    service = ReturnShuffleService()

    first = service.shuffled_prices(prices, seed=42)
    second = service.shuffled_prices(prices, seed=42)
    third = service.shuffled_prices(prices, seed=43)

    assert first.equals(second)
    assert not first.equals(third)


def test_shuffling_candles_keeps_the_intrabar_shape():
    prices = make_prices(200)
    candles = pd.DataFrame(
        {
            "open": prices * 0.999,
            "high": prices * 1.004,
            "low": prices * 0.996,
            "close": prices,
            "volume": 1.0,
            "quote_volume": 1.0,
            "taker_buy_base_volume": 0.5,
            "taker_buy_quote_volume": 0.5,
            "trade_count": 10,
        }
    )
    series = CandleSeries(INSTRUMENT, candles)

    shuffled = ReturnShuffleService().shuffled_candles(series, seed=3)
    frame = shuffled.frame

    # 高低價相對於收盤價的比例保持不變，所以 ATR 之類的特徵不會歸零
    np.testing.assert_allclose(
        (frame["high"] / frame["close"]).to_numpy(),
        (candles["high"] / candles["close"]).to_numpy(),
        rtol=1e-12,
    )
    assert (frame["high"] >= frame["close"]).all()
    assert (frame["low"] <= frame["close"]).all()
    # 成交量原封不動：這個示範只改一個變數
    np.testing.assert_allclose(frame["volume"].to_numpy(), candles["volume"].to_numpy())


def test_too_little_data_or_a_non_positive_price_is_rejected():
    index = pd.date_range("2026-01-01", periods=2, freq="1h", tz="UTC")

    with pytest.raises(ValueError, match="至少要 3 根"):
        ReturnShuffleService().shuffled_prices(
            pd.Series([1.0, 2.0], index=index), seed=1
        )

    three = pd.date_range("2026-01-01", periods=3, freq="1h", tz="UTC")
    with pytest.raises(ValueError, match="必須為正"):
        ReturnShuffleService().shuffled_prices(
            pd.Series([1.0, 0.0, 2.0], index=three), seed=1
        )
