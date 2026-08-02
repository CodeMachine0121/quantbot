# tests/domain/indicators/test_sma.py
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.crossover_signals import CrossoverSignals
from quantbot.domain.indicators.irregular_index_error import IrregularIndexError
from quantbot.domain.indicators.sma import SMA
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe

HOURLY = Timeframe("1h")
INSTRUMENT = Instrument(symbol="BTC/USDT", market=Market.SPOT, timeframe=HOURLY)


def make_series(closes: list[float]) -> CandleSeries:
    """建一段測試用的 K 線。只有 close 有意義，其他欄位補得過得去就好。"""
    index = pd.date_range(
        "2026-01-01", periods=len(closes), freq="1h", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": 1.0,
            },
            index=index,
        ),
    )


def test_matches_hand_computed_values():
    result = SMA(3).compute(make_series([1, 2, 3, 4, 5]))
    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_output_name_and_warmup_come_from_the_instance():
    indicator = SMA(20)
    assert indicator.name == "sma_20"
    assert indicator.warmup_bar_count == 19  # 只有 SMA 是 n-1
    assert indicator.compute(make_series([1.0] * 25)).name == "sma_20"


def test_index_is_never_changed():
    series = make_series([float(i) for i in range(30)])
    assert SMA(5).compute(series).index.equals(series.frame.index)


def test_warmup_stays_nan_and_is_not_filled():
    assert SMA(3).compute(make_series([10, 20, 30, 40])).isna().sum() == 2


def test_insufficient_data_returns_all_nan():
    """資料比視窗短：回傳等長的全 NaN，不是丟例外，也不是回傳短序列。"""
    result = SMA(20).compute(make_series([100, 101, 102]))
    assert len(result) == 3
    assert result.isna().all()


def test_single_bar():
    assert SMA(20).compute(make_series([42.0])).isna().all()
    assert SMA(1).compute(make_series([42.0])).iloc[0] == pytest.approx(42.0)


def test_empty_series():
    assert SMA(20).compute(make_series([])).empty


def test_missing_bars_raise_when_the_timeframe_is_declared():
    series = make_series([1, 2, 3, 4, 5])
    gapped = CandleSeries(INSTRUMENT, series.frame.drop(index=series.open_times[2]))

    with pytest.raises(IrregularIndexError):
        SMA(3, expected_timeframe=HOURLY).compute(gapped)


def test_missing_bars_silently_widen_the_window_without_the_check():
    """沒宣告 expected_timeframe 時，缺漏會安靜地讓視窗變長。這個測試把行為釘住。"""
    series = make_series([1, 2, 3, 4, 5])
    gapped = CandleSeries(INSTRUMENT, series.frame.drop(index=series.open_times[2]))

    assert SMA(3).compute(gapped).iloc[2] == pytest.approx((1 + 2 + 4) / 3)


def test_invalid_period_is_rejected_at_construction():
    """視窗長度是建構參數，所以錯的值在建物件時就擋掉，不必等到算完。"""
    with pytest.raises(ValueError):
        SMA(0)


def test_candle_series_sorts_so_the_indicator_can_trust_the_order():
    """指標裡沒有「index 有沒有排序」的檢查，因為 CandleSeries 保證了它。

    把不變式放進型別，下游就不必各自防禦——而這條保證要有測試盯著。
    """
    series = make_series([1, 2, 3])
    reversed_series = CandleSeries(INSTRUMENT, series.frame.iloc[::-1])

    assert reversed_series.open_times.is_monotonic_increasing
    assert SMA(2).compute(reversed_series).iloc[-1] == pytest.approx(2.5)


def test_crossover_fires_once_on_the_crossing_bar():
    fast = pd.Series([1, 2, 3, 4, 3, 2], dtype="float64")
    slow = pd.Series([3, 3, 3, 3, 3, 3], dtype="float64")
    crosses = CrossoverSignals(fast, slow)

    assert crosses.golden.tolist() == [False, False, False, True, False, False]
    assert crosses.death.tolist() == [False, False, False, False, True, False]
    assert list(crosses.table.columns) == ["golden", "death"]


def test_crossover_ignores_the_first_bar_that_has_values():
    """慢線第一次有值的那一根，即使快線在上面也不算交叉。"""
    fast = pd.Series([float("nan"), float("nan"), 5.0, 6.0])
    slow = pd.Series([float("nan"), float("nan"), 4.0, 4.0])
    assert not CrossoverSignals(fast, slow).golden.iloc[2]


def test_entry_is_the_golden_cross_shifted_by_one_bar():
    fast = pd.Series([1, 2, 3, 4, 3, 2], dtype="float64")
    slow = pd.Series([3, 3, 3, 3, 3, 3], dtype="float64")
    crosses = CrossoverSignals(fast, slow)

    assert crosses.golden.tolist() == [False, False, False, True, False, False]
    assert crosses.entry.tolist() == [False, False, False, False, True, False]
