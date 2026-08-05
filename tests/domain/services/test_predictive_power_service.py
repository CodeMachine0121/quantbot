import numpy as np
import pandas as pd
import pytest

from quantbot.domain.services.predictive_power_service import PredictivePowerService


def series(values, *, name: str = "feature") -> pd.Series:
    index = pd.date_range("2026-08-04", periods=len(values), freq="1s", tz="UTC")
    return pd.Series(values, index=index, name=name)


def test_forward_returns_look_forward_not_backward():
    """對齊只有一種是對的：第 0 格的 forward 是第 horizon 格的報酬。"""
    prices = series([100.0, 101.0, 103.0, 106.0])

    forward = PredictivePowerService.forward_returns(prices, horizon=1)

    assert forward.iloc[0] == pytest.approx(0.01)
    assert forward.iloc[1] == pytest.approx(2 / 101)
    assert pd.isna(forward.iloc[-1])  # 最後一格沒有未來
    assert forward.name == "forward_1"


def test_forward_returns_drops_pairs_that_span_a_recording_gap():
    """shift() 只認得「第幾格」，不認得時間。

    這裡的第 2 與第 3 筆中間空了二十分鐘（錄製中斷）。沒有 maximum_step 的話，
    那一對會被當成「往後一筆」，於是一個一秒的報酬實際上跨了二十分鐘——
    而那種列的報酬大得離譜，足以主導整個相關係數。
    """
    index = pd.DatetimeIndex(
        [
            "2026-08-04T16:52:00Z",
            "2026-08-04T16:52:01Z",
            "2026-08-04T17:12:00Z",  # 中斷之後才回來
            "2026-08-04T17:12:01Z",
        ]
    )
    prices = pd.Series([100.0, 100.1, 130.0, 130.2], index=index, name="mid_price")

    without_bound = PredictivePowerService.forward_returns(prices, horizon=1)
    with_bound = PredictivePowerService.forward_returns(
        prices, horizon=1, maximum_step=pd.Timedelta(seconds=5)
    )

    assert without_bound.iloc[1] == pytest.approx(0.2987, abs=1e-4)  # 跨越空白
    assert pd.isna(with_bound.iloc[1])
    assert with_bound.iloc[0] == pytest.approx(0.001)  # 正常的那些不受影響
    assert with_bound.iloc[2] == pytest.approx(0.2 / 130.0)


def test_forward_returns_rejects_a_zero_horizon():
    with pytest.raises(ValueError):
        PredictivePowerService.forward_returns(series([1.0, 2.0]), horizon=0)


def test_a_feature_that_is_the_future_gets_a_perfect_score():
    """自我檢查：把未來報酬本身當特徵，IC 應該接近 1。

    這個測試在驗**驗證工具本身**。如果連這種極端情況都量不出高相關，
    那之後所有「這個特徵沒用」的結論都不能信——可能是工具壞了。
    """
    generator = np.random.default_rng(20260924)
    prices = series(100 * np.exp(np.cumsum(generator.normal(0, 0.001, 800))))
    forward = PredictivePowerService.forward_returns(prices, horizon=1)

    report = PredictivePowerService().evaluate(forward.rename("cheating"), forward)

    assert report.information_coefficient == pytest.approx(1.0)
    assert report.is_monotonic


def test_pure_noise_gets_an_information_coefficient_near_zero():
    generator = np.random.default_rng(7)
    prices = series(100 * np.exp(np.cumsum(generator.normal(0, 0.001, 2_000))))
    noise = series(generator.normal(0, 1, 2_000), name="noise")

    report = PredictivePowerService().evaluate(
        noise, PredictivePowerService.forward_returns(prices, horizon=5)
    )

    assert abs(report.information_coefficient) < 0.05
    assert abs(report.t_statistic) < 2.0  # 跟 0 分不出來


def test_sample_count_and_t_statistic_move_together():
    """同一個相關係數，樣本數不同代表的意義完全不同。

    這是報告一定要帶樣本數的理由：小樣本上的 0.2 可能只是雜訊。
    """
    small = PredictivePowerService._t_statistic(0.2, 30)
    large = PredictivePowerService._t_statistic(0.2, 3_000)

    assert abs(small) < 2.0
    assert abs(large) > 2.0


def test_buckets_are_equally_sized_and_ordered():
    generator = np.random.default_rng(11)
    count = 1_000
    feature = series(generator.normal(0, 1, count))
    # 讓未來報酬跟特徵有真實的關係，再加一點雜訊
    forward = (feature * 0.002 + generator.normal(0, 0.001, count)).rename("forward_1")

    report = PredictivePowerService(bucket_count=5).evaluate(feature, forward)

    assert report.sample_count == count
    assert len(report.bucket_mean_returns) == 5
    assert report.is_monotonic
    assert report.top_minus_bottom > 0


def test_a_reversed_relationship_shows_up_as_a_negative_coefficient():
    generator = np.random.default_rng(12)
    feature = series(generator.normal(0, 1, 600))
    forward = (-feature * 0.002).rename("forward_1")

    report = PredictivePowerService().evaluate(feature, forward)

    assert report.information_coefficient < -0.9
    assert not report.is_monotonic  # 遞減不算單調遞增
    assert report.top_minus_bottom < 0


def test_too_few_samples_raises_instead_of_reporting_a_number():
    """樣本不夠時 NEVER 回一個看起來像結論的數字。"""
    with pytest.raises(ValueError, match="樣本"):
        PredictivePowerService(bucket_count=5).evaluate(
            series([1.0, 2.0, 3.0]), series([0.1, 0.2, 0.3], name="forward_1")
        )


def test_bucket_count_must_be_at_least_two():
    with pytest.raises(ValueError):
        PredictivePowerService(bucket_count=1)


def test_nan_pairs_are_dropped_not_filled():
    """暖機期與「沒錄到」都是 NaN，兩者都該被排除而不是補值。"""
    feature = series([np.nan, np.nan, *np.linspace(-1, 1, 98)])
    forward = series([*np.linspace(-0.01, 0.01, 98), np.nan, np.nan], name="forward_1")

    report = PredictivePowerService(bucket_count=4).evaluate(feature, forward)

    assert report.sample_count == 96
