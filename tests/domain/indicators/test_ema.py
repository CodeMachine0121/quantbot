# tests/domain/indicators/test_ema.py
import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.ema import EMA
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from tests.reference.reference_ema import ReferenceEMA

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)
# 起始值的差異要幾百根才衰減到浮點精度以下，跨實作比對前要丟掉這段
STABLE_AFTER_BARS = 300


def make_series(closes: list[float]) -> CandleSeries:
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


def random_closes(count: int = 500, seed: int = 20260919) -> np.ndarray:
    generator = np.random.default_rng(seed)
    return 62000 * np.exp(np.cumsum(generator.normal(0, 0.01, count)))


def test_matches_the_reference_implementation():
    closes = random_closes()
    mine = EMA(20).compute(make_series(closes.tolist())).to_numpy()
    theirs = ReferenceEMA(20).compute(closes)

    assert np.nanmax(np.abs(mine - theirs)) < 1e-9


def test_matches_pandas_ta_after_the_warmup():
    """pandas-ta 預設 adjust=False 且用前 n 根 SMA 當種子，跟 warmup="sma" 對齊。"""
    pandas_ta = pytest.importorskip("pandas_ta")
    series = make_series(random_closes(1000).tolist())

    difference = (
        EMA(20).compute(series) - pandas_ta.ema(series.frame["close"], length=20)
    ).abs()
    assert difference.iloc[STABLE_AFTER_BARS:].max() < 1e-9


def test_alpha_is_two_over_n_plus_one():
    """明天的 Wilder 平滑用的是 1/n，跟這裡差將近一倍，所以先把公式釘住。"""
    assert EMA(20).alpha == pytest.approx(2 / 21)
    assert EMA(14).alpha == pytest.approx(2 / 15)


def test_constant_series_equals_the_constant():
    """輸入是常數時，EMA 必須等於那個常數，這是加權平均的基本性質。"""
    result = EMA(20).compute(make_series([100.0] * 50)).dropna()
    assert np.allclose(result.to_numpy(), 100.0)


def test_sma_warmup_leaves_leading_nan():
    result = EMA(20).compute(make_series([float(i) for i in range(30)]))

    assert result.iloc[: 20 - 1].isna().all()
    # 第 20 根就是前 20 根的算術平均
    assert result.iloc[19] == pytest.approx(np.mean(range(20)))


def test_insufficient_data_returns_all_nan():
    """只有 10 根卻要算 EMA(20)：全部回 NaN，NEVER 硬擠一個值出來。"""
    result = EMA(20).compute(make_series([float(i) for i in range(10)]))

    assert len(result) == 10
    assert result.isna().all()


def test_single_bar():
    series = make_series([42000.0])
    assert EMA(20).compute(series).isna().all()
    # warmup="first" 時，唯一那根就是它自己
    assert EMA(20, warmup="first").compute(series).iloc[0] == 42000.0


def test_gap_is_carried_not_filled():
    """缺漏那一格沿用前值是 ewm 的行為。用測試把它釘住，
    免得哪天有人加了 fillna 卻沒人發現。"""
    result = EMA(3, warmup="first").compute(
        make_series([100.0, 101.0, float("nan"), 103.0])
    )

    assert result.iloc[2] == pytest.approx(result.iloc[1])
    # 102.375 而不是 101.75：ignore_na 預設 False，缺漏那一格「時間有過去」，
    # 所以舊值多衰減了一次，新資料的相對權重變大
    assert result.iloc[3] == pytest.approx(102.375)


def test_required_warmup_is_a_number_callers_can_ask_for():
    assert EMA(20).required_warmup_bar_count() == 100
    assert EMA(20).required_warmup_bar_count(safety_factor=10) == 200


def test_invalid_arguments_are_rejected_at_construction():
    with pytest.raises(ValueError):
        EMA(0)
    with pytest.raises(ValueError):
        EMA(5, warmup="exponential")
