import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.features.trading_activity import TradingActivity
from quantbot.domain.values.activity_baseline import ActivityBaseline
from quantbot.domain.values.activity_measure import ActivityMeasure
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_view(
    *,
    trade_counts: list[int] | np.ndarray,
    closes: list[float] | np.ndarray | None = None,
    volumes: list[float] | np.ndarray | None = None,
) -> MarketView:
    count = len(trade_counts)
    index = pd.date_range(
        "2026-07-01", periods=count, freq="1h", tz="UTC", name="open_time"
    )
    prices = np.full(count, 65_000.0) if closes is None else np.asarray(closes)
    return MarketView(
        candles=CandleSeries(
            INSTRUMENT,
            pd.DataFrame(
                {
                    "open": prices,
                    "high": prices,
                    "low": prices,
                    "close": prices,
                    "volume": (
                        np.ones(count) if volumes is None else np.asarray(volumes)
                    ),
                    "trade_count": np.asarray(trade_counts),
                },
                index=index,
            ),
        )
    )


def jittered(count: int, *, centre: int = 1_000, seed: int = 20260926) -> np.ndarray:
    """有一點自然起伏的基準序列。

    完全固定的序列標準差是 0，z-score 沒有定義——測試資料不能比真實資料更乾淨，
    否則測到的是一個不存在的情況。
    """
    generator = np.random.default_rng(seed)
    return generator.normal(centre, centre * 0.05, count).round().astype(int)


def test_a_spike_scores_high_and_a_normal_bar_scores_near_zero():
    counts = np.append(jittered(40), [1_050, 5_000])
    view = make_view(trade_counts=counts)

    scores = TradingActivity(window=20).compute(view)

    assert abs(scores.iloc[-2]) < 3.0  # 只比平常多 5%
    assert scores.iloc[-1] > 10.0  # 五倍暴量


def test_the_rolling_window_excludes_the_current_bar():
    """當根被算進基準的話，暴量的 K 線會自己把基準拉高，z-score 被系統性低估。

    這裡用一段完全平穩的資料加上最後一根暴量：如果視窗含當根，最後一根的
    標準差會被自己撐大，z-score 就縮小了。
    """
    counts = np.append(jittered(30), 3_000)
    view = make_view(trade_counts=counts)
    values = view.candles.frame["trade_count"].astype("Float64").astype("float64")

    excluding = TradingActivity(window=10).compute(view).iloc[-1]

    including_history = values.rolling(10)
    including = ((values - including_history.mean()) / including_history.std()).iloc[-1]

    assert excluding > including * 2


def test_zero_deviation_is_nan_not_infinity():
    """完全沒有變化的那段，異常程度沒有定義。"""
    view = make_view(trade_counts=[1_000] * 30)

    scores = TradingActivity(window=10).compute(view)

    assert scores.isna().all()


def test_warmup_leaves_the_first_window_empty():
    generator = np.random.default_rng(8)
    view = make_view(trade_counts=generator.integers(500, 1_500, 100))
    feature = TradingActivity(window=20)

    scores = feature.compute(view)

    assert scores.iloc[:20].isna().all()
    assert scores.iloc[20:].notna().all()
    assert feature.warmup_bar_count == 20


def test_hour_of_day_baseline_only_uses_the_past():
    """整段樣本算鐘點平均是未來函數。這裡證明實作用的是逐步展開的基準。

    資料是 20 天的每小時，鐘點 3 一直很冷清（100 筆），最後一天的鐘點 3 突然
    暴量到 10,000。如果基準用了整段樣本，那個 10,000 會被算進鐘點 3 的平均與
    標準差裡，把自己的 z-score 壓下來。
    """
    day_count = 20
    generator = np.random.default_rng(3)
    counts = []
    for day in range(day_count):
        for hour in range(24):
            if hour == 3:
                quiet = generator.normal(100, 5)
                counts.append(10_000 if day == day_count - 1 else int(quiet))
            else:
                counts.append(int(generator.normal(1_000 + hour * 10, 50)))
    view = make_view(trade_counts=counts)

    scores = TradingActivity(baseline=ActivityBaseline.HOUR_OF_DAY, window=5).compute(
        view
    )
    values = view.candles.frame["trade_count"].astype("Float64").astype("float64")

    expanding_score = scores.iloc[-21]  # 最後一天的鐘點 3

    hour = pd.Series(pd.DatetimeIndex(values.index).hour, index=values.index)
    grouped = values.groupby(hour)
    naive = ((values - grouped.transform("mean")) / grouped.transform("std")).iloc[-21]

    assert expanding_score > 100  # 對過去的鐘點 3 來說這是天文數字
    assert naive < 5  # 用了未來資料的版本把自己攤平了


def test_hour_of_day_baseline_needs_more_history_than_the_rolling_one():
    """每個鐘點各自累積歷史，所以前幾天沒有值。"""
    counts = [1_000 + (index % 24) * 10 + index for index in range(24 * 5)]
    view = make_view(trade_counts=counts)

    scores = TradingActivity(baseline=ActivityBaseline.HOUR_OF_DAY).compute(view)

    assert scores.iloc[:48].isna().all()  # 每個鐘點至少要出現過兩次
    assert scores.iloc[-24:].notna().all()


@pytest.mark.parametrize(
    "measure",
    [
        ActivityMeasure.TRADE_COUNT,
        ActivityMeasure.VOLUME,
        ActivityMeasure.ABSOLUTE_RETURN,
    ],
)
def test_every_measure_produces_an_aligned_series(measure):
    generator = np.random.default_rng(9)
    count = 200
    view = make_view(
        trade_counts=generator.integers(500, 1_500, count),
        volumes=generator.uniform(1, 50, count),
        closes=65_000 * np.exp(np.cumsum(generator.normal(0, 0.002, count))),
    )
    feature = TradingActivity(measure=measure, window=30)

    scores = feature.compute(view)

    assert scores.index.equals(view.candles.frame.index)
    assert scores.name == f"activity_{measure}_rolling_30"
    assert scores.iloc[40:].notna().all()


def test_the_three_measures_disagree():
    """成交量一樣、筆數差很多的那種 K 線，兩個量給出不同的答案。

    這是 Day 09 那兩根 K 線的合成版：後半段成交量不變，但筆數變四倍。
    """
    count = 61
    trade_counts = np.append(jittered(count - 1), 4_000)
    volumes = [10.0] * count  # 成交量完全不動，所以它的 z-score 沒有定義
    view = make_view(trade_counts=trade_counts, volumes=volumes)

    by_count = TradingActivity(measure=ActivityMeasure.TRADE_COUNT, window=30).compute(
        view
    )
    by_volume = TradingActivity(measure=ActivityMeasure.VOLUME, window=30).compute(view)

    assert by_count.iloc[-1] > 3.0
    assert by_volume.iloc[-1] != by_volume.iloc[-1] or pd.isna(by_volume.iloc[-1])


def test_rejects_a_window_too_small_for_a_standard_deviation():
    with pytest.raises(ValueError):
        TradingActivity(window=1)
