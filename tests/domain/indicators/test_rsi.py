# tests/domain/indicators/test_rsi.py
import numpy as np
import pandas as pd
import pytest

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.indicators.ema import EMA
from quantbot.domain.indicators.registry import INDICATORS
from quantbot.domain.indicators.rsi import RSI, WilderSmoother
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.timeframe import Timeframe
from tests.reference.reference_rsi import ReferenceRSI

PERIOD = 14
# 起始值差異需要約 20 倍週期才會衰減到浮點精度以下，跨實作比對前要丟掉這段
STABLE_AFTER_BARS = 300
INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1h")
)


def make_series(closes: np.ndarray | list[float]) -> CandleSeries:
    values = list(closes)
    index = pd.date_range(
        "2026-01-01", periods=len(values), freq="1h", tz="UTC", name="open_time"
    )
    return CandleSeries(
        INSTRUMENT,
        pd.DataFrame(
            {
                "open": values,
                "high": values,
                "low": values,
                "close": values,
                "volume": 1.0,
            },
            index=index,
        ),
    )


def random_closes(count: int = 2000, seed: int = 20260920) -> np.ndarray:
    generator = np.random.default_rng(seed)
    return 60_000 * np.exp(np.cumsum(generator.normal(0, 0.004, count)))


def test_matches_the_loop_reference():
    series = make_series(random_closes())
    assert np.allclose(
        RSI(PERIOD).compute(series).to_numpy(),
        ReferenceRSI(PERIOD).compute(series.frame["close"]).to_numpy(),
        equal_nan=True,
        atol=1e-10,
    )


def test_wilder_alpha_is_one_over_n_not_two_over_n_plus_one():
    """寫成 span=n 的話這裡會變成 EMA 的係數，是本篇最容易出的錯。

    兩個係數並排斷言，比寫十行註解有用：n=14 時差了將近一倍。
    """
    assert WilderSmoother(PERIOD).alpha == pytest.approx(1 / PERIOD)
    assert EMA(PERIOD).alpha == pytest.approx(2 / (PERIOD + 1))
    assert EMA(PERIOD).alpha > WilderSmoother(PERIOD).alpha * 1.8


def test_matches_pandas_ta_after_the_warmup():
    pandas_ta = pytest.importorskip("pandas_ta")
    series = make_series(random_closes())

    difference = (
        RSI(PERIOD).compute(series)
        - pandas_ta.rsi(series.frame["close"], length=PERIOD)
    ).abs()
    assert difference.iloc[STABLE_AFTER_BARS:].max() < 1e-9


def test_output_contract():
    series = make_series(random_closes(100))
    indicator = RSI(PERIOD)
    result = indicator.compute(series)

    assert result.index.equals(series.frame.index)  # index 不動
    assert result.name == f"rsi_{PERIOD}"  # 命名慣例
    assert indicator.warmup_bar_count == PERIOD  # 暖機期問得到
    assert result.iloc[:PERIOD].isna().all()
    assert result.iloc[PERIOD:].notna().all()
    assert result.iloc[PERIOD:].between(0, 100).all()


def test_registry_builds_a_working_indicator():
    """Day 15 的 pipeline 只會這樣用它：用字串建物件、問暖機、再算。"""
    indicator = INDICATORS["rsi"](PERIOD)

    assert isinstance(indicator, RSI)
    assert indicator.warmup_bar_count == PERIOD
    assert indicator.compute(make_series(random_closes(100))).name == f"rsi_{PERIOD}"


def test_registry_warmup_is_the_longest_of_the_chain():
    wanted = [("ema", 12), ("ema", 26), ("rsi", 14)]
    indicators = [INDICATORS[name](period) for name, period in wanted]

    assert max(indicator.warmup_bar_count for indicator in indicators) == 26


def test_insufficient_data_returns_all_nan():
    result = RSI(PERIOD).compute(make_series(random_closes(PERIOD)))
    assert len(result) == PERIOD and result.isna().all()


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (np.arange(100, 140, 1.0), 100.0),  # 全漲
        (np.arange(140, 100, -1.0), 0.0),  # 全跌
        (np.full(40, 100.0), 50.0),  # 完全持平，補中性值
    ],
)
def test_degenerate_series(closes, expected):
    assert RSI(PERIOD).compute(make_series(closes)).iloc[-1] == pytest.approx(expected)


def test_gap_does_not_surface_as_nan():
    """釘住已知行為：缺漏不會變成 NaN，只會讓數值悄悄偏掉。

    這是 ewm() 跳過 NaN 的結果。缺漏 MUST 在入庫階段處理（Day 07-08），
    指標不負責修資料。
    """
    closes = random_closes()
    complete = make_series(closes)

    gapped_closes = closes.copy()
    gapped_closes[300:305] = np.nan
    gapped = make_series(gapped_closes)

    result = RSI(PERIOD).compute(gapped)
    assert result.iloc[300:305].notna().all()
    assert result.iloc[300:305].eq(result.iloc[300]).all()
    assert (RSI(PERIOD).compute(complete) - result).abs().max() > 1.0


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        RSI(period=0)  # 建構時就擋掉
    with pytest.raises(KeyError):
        RSI(PERIOD, column="typical_price").compute(make_series(random_closes(50)))
