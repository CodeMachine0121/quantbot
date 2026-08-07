# quantbot/domain/features/distance_to_point_of_control.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.services.volume_profile_service import VolumeProfileService
from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class DistanceToPointOfControl:
    """現在的價格離 POC 多遠，以 POC 的百分比表示。實作 domain 的 Feature。

    Volume Profile 本身進不了特徵管線——它的 index 是價格，跟 K 線對不齊。能進管線
    的是**從它算出來的純量**，而這是最有用的那一個：價格相對於籌碼密集區的位置。

    滾動視窗的部分要小心：每一根 K 線的 POC 都必須只用**那根之前**的資料算。用整段
    資料算一個 POC 再套到每一根上，就是 Day 12 那個鐘點基準的錯誤換一種形狀——
    在 2025 年 3 月那一根上，POC 裡含著 2026 年的成交。

    代價是它算得慢：每一根都要重算一次分布。所以視窗用「天」而不是「根」來表達，
    而且預設值刻意保守。這是這一階段第一個**不能向量化**的特徵，理由跟 Day 05 的
    EMA 不同——EMA 是遞迴，這個是每一步的輸入集合都不一樣。
    """

    def __init__(
        self, *, window_days: int = 5, service: VolumeProfileService | None = None
    ) -> None:
        if window_days < 1:
            raise ValueError(f"window_days 必須 >= 1，收到 {window_days}")
        self.window_days = window_days
        self._service = service or VolumeProfileService()

    @property
    def name(self) -> str:
        return f"distance_to_poc_{self.window_days}d"

    @property
    def warmup_bar_count(self) -> int:
        """至少要一個完整視窗。以根數表達要知道一天幾根，所以這裡回一個下限，
        實際的暖機由第一個非 NaN 決定（跟 Day 12 的鐘點基準同一個情況）。"""
        return self.window_days

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        candles = view.candles
        window = pd.Timedelta(days=self.window_days)
        closes = candles.frame["close"].astype("float64")

        distances = [
            self._distance_at(candles, moment, window, float(close))
            for moment, close in zip(candles.open_times, closes, strict=True)
        ]
        return pd.Series(
            distances, index=candles.frame.index, dtype="float64", name=self.name
        )

    def _distance_at(
        self,
        candles: CandleSeries,
        moment: pd.Timestamp,
        window: pd.Timedelta,
        close: float,
    ) -> float:
        """這一根的距離。視窗是 [moment − window, moment)，**右端開區間排除當根**。"""
        times = candles.open_times
        selected = (times >= moment - window) & (times < moment)
        history = candles.frame.loc[selected]
        if history.empty:
            return float("nan")

        profile = self._service.from_candles(CandleSeries(candles.instrument, history))
        point_of_control = profile.point_of_control
        return (close - point_of_control) / point_of_control


class DistanceToPointOfControlBuilder:
    """設定檔的 distance_to_poc。分桶數影響 POC，所以它也是設定得到的參數。"""

    @property
    def kind(self) -> str:
        return "distance_to_poc"

    def build(self, parameters: FeatureParameters) -> DistanceToPointOfControl:
        return DistanceToPointOfControl(
            window_days=parameters.integer("window_days", 5),
            service=VolumeProfileService(
                bucket_count=parameters.integer("bucket_count", 100)
            ),
        )
