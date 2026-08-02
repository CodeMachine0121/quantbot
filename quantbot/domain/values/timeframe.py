# quantbot/domain/values/timeframe.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar

import pandas as pd

from quantbot.domain.values.time_range import TimeRange


@dataclass(frozen=True)
class Timeframe:
    """K 線的粒度，以及由它推導出的所有換算。

    「一根多長」「pandas 的 freq 字串是什麼」「這根收完了沒」「這段期間該有
    哪些開盤時間」是同一份知識的四個面向，所以它們住在一起。
    NEVER 在別處再寫第二份 timeframe 對照表。
    """

    value: str

    # Binance 的 timeframe 字串跟 pandas 的 freq 字串不一樣：pandas 的 "1m" 不是分鐘
    PANDAS_FREQUENCIES: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "1s": "1s",
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "1h": "1h",
            "4h": "4h",
            "1d": "1D",
        }
    )

    def __post_init__(self) -> None:
        if self.value not in self.PANDAS_FREQUENCIES:
            raise ValueError(f"未知的 timeframe：{self.value}")

    @property
    def pandas_frequency(self) -> str:
        return self.PANDAS_FREQUENCIES[self.value]

    @property
    def step(self) -> pd.Timedelta:
        """一根 K 線的長度。"""
        return pd.Timedelta(self.pandas_frequency)

    def floor(self, moment: pd.Timestamp) -> pd.Timestamp:
        """moment 落在哪一根 K 線裡，回傳那根的開盤時間。"""
        return moment.floor(self.pandas_frequency)

    def latest_closed_open_time(self, now: pd.Timestamp) -> pd.Timestamp:
        """最後一根**已經收盤**的 K 線的開盤時間。

        floor(now) 是當下那根還在跳動的 K 線，所以要再退一格。
        """
        return self.floor(now) - self.step

    def expected_open_times(self, period: TimeRange) -> pd.DatetimeIndex:
        """這段期間內所有應該存在的開盤時間，一律 UTC。"""
        return pd.date_range(
            start=period.start.ceil(self.pandas_frequency),
            end=period.end,
            freq=self.pandas_frequency,
            tz="UTC",
            inclusive="left",
        )

    def __str__(self) -> str:
        return self.value
