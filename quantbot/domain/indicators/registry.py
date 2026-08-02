# quantbot/domain/indicators/registry.py
from collections.abc import Mapping
from types import MappingProxyType

from quantbot.domain.indicators.ema import EMA
from quantbot.domain.indicators.indicator import Indicator
from quantbot.domain.indicators.rsi import RSI
from quantbot.domain.indicators.sma import SMA

# 註冊表裡放的是**類別**而不是函式，所以取出來之後可以先問它問題、再算。
# Day 15 會把它擴充成完整的特徵註冊表。
INDICATORS: Mapping[str, type[Indicator]] = MappingProxyType(
    {
        "sma": SMA,
        "ema": EMA,
        "rsi": RSI,
    }
)
