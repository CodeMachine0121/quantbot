# quantbot/domain/features/trading_activity.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.activity_baseline import ActivityBaseline
from quantbot.domain.values.activity_measure import ActivityMeasure
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class TradingActivity:
    """交易活躍度：這一根比「平常」熱多少，以標準差為單位。實作 domain 的 Feature。

    絕對值沒有用。BTC 一分鐘成交 12 顆是稀鬆平常，某個小幣一分鐘成交 12 顆是暴量；
    同一個 BTC，歐洲時段開盤的 12 顆跟亞洲深夜的 12 顆也不是同一件事。所以這個特徵
    輸出的是 **z-score**：(現在 − 平常) / 平常的標準差。無單位，跨交易對與跨時段可比。

    z-score 的分母是標準差，所以它有一個必須處理的退化情況：標準差為 0（那段完全
    沒有變化）時商是無限大。那時候回 NaN——「沒有變化」的異常程度沒有定義。
    """

    def __init__(
        self,
        *,
        measure: ActivityMeasure = ActivityMeasure.TRADE_COUNT,
        baseline: ActivityBaseline = ActivityBaseline.ROLLING,
        window: int = 60,
    ) -> None:
        if window < 2:
            raise ValueError(f"window 必須 >= 2（要算標準差），收到 {window}")
        self.measure = measure
        self.baseline = baseline
        self.window = window

    @property
    def name(self) -> str:
        return f"activity_{self.measure}_{self.baseline}_{self.window}"

    @property
    def warmup_bar_count(self) -> int:
        """滾動基準要滿一個視窗。

        鐘點基準要的更多：每個鐘點各自需要 window 個樣本，而一天只出現一次某個
        鐘點，所以真正的暖機是 window 天。以根數表達的話是 window × 一天幾根，
        而「一天幾根」取決於 timeframe，這個類別不知道。所以這裡回一個誠實的
        下限，實際的暖機由第一個非 NaN 決定——這也是為什麼管線要靠 NaN 而不是
        只靠這個數字來切暖機期。
        """
        return self.window

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        values = self.measure.of(view.candles.frame)
        if self.baseline is ActivityBaseline.ROLLING:
            return self._rolling_z_score(values).rename(self.name)
        return self._hour_of_day_z_score(values).rename(self.name)

    def _rolling_z_score(self, values: pd.Series) -> pd.Series:
        """跟最近 window 根比。

        **視窗要排除當根**：shift(1) 之後再 rolling。不排除的話，當根自己會被算進
        「平常」的平均與標準差裡，於是一根暴量的 K 線會自己把基準拉高，z-score
        因此被系統性低估。這是未來函數的近親——不是偷看未來，是把當下混進歷史。
        """
        history = values.shift(1).rolling(self.window)
        deviation = history.std()
        return (values - history.mean()) / deviation.where(deviation > 0)

    def _hour_of_day_z_score(self, values: pd.Series) -> pd.Series:
        """跟同一個鐘點的歷史比，而且只用**過去**的同鐘點資料。

        直覺的寫法是 values.groupby(hour).transform("mean")，一行就好。但那個平均
        用了整段樣本，包含未來——在 2026-03-01 那天，基準裡含著 2026-08 的資料。
        回測時這種寫法會讓活躍度過濾條件看起來特別靈，因為它知道後面會發生什麼。

        正確的寫法是 shift(1) 之後 expanding()：每個鐘點各自往前累積自己的歷史。
        代價是前面幾天沒有值（每個鐘點都要先看過至少兩次），這是應該付的代價。
        """
        hour = pd.Series(pd.DatetimeIndex(values.index).hour, index=values.index)
        grouped = values.groupby(hour)
        history = grouped.shift(1)
        mean = history.groupby(hour).expanding().mean().reset_index(level=0, drop=True)
        deviation = (
            history.groupby(hour).expanding().std().reset_index(level=0, drop=True)
        )
        return (values - mean) / deviation.where(deviation > 0)


class TradingActivityBuilder:
    """設定檔的 activity。measure 與 baseline 都是列舉，錯字要在載入時就擋掉。"""

    @property
    def kind(self) -> str:
        return "activity"

    def build(self, parameters: FeatureParameters) -> TradingActivity:
        measure = parameters.text("measure", ActivityMeasure.TRADE_COUNT.value)
        if measure not in tuple(ActivityMeasure):
            raise ValueError(
                f"measure 只能是 {[value.value for value in ActivityMeasure]}，"
                f"實得 {measure!r}"
            )
        baseline = parameters.text("baseline", ActivityBaseline.ROLLING.value)
        if baseline not in tuple(ActivityBaseline):
            raise ValueError(
                f"baseline 只能是 {[value.value for value in ActivityBaseline]}，"
                f"實得 {baseline!r}"
            )
        return TradingActivity(
            measure=ActivityMeasure(measure),
            baseline=ActivityBaseline(baseline),
            window=parameters.integer("window", 60),
        )
