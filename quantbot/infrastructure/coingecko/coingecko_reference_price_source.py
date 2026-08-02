# quantbot/infrastructure/coingecko/coingecko_reference_price_source.py
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

import httpx
import pandas as pd

from quantbot.domain.values.time_range import TimeRange


class CoinGeckoReferencePriceSource:
    """CoinGecko 這個對照組。實作 domain 的 ReferencePriceSource。

    它給的是跨交易所的 USD 參考價，跟單一交易所的 USDT 成交價本來就不會相等，
    所以它抓的是量級錯誤——欄位對映錯一格、時間戳單位搞錯、抓成永續合約。
    比對邏輯不在這裡，在 domain 的 PriceCrossCheckService。
    """

    BASE_URL: ClassVar[str] = "https://api.coingecko.com/api/v3"
    COIN_IDENTIFIERS: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "BTC/USDT": "bitcoin",
            "ETH/USDT": "ethereum",
            "SOL/USDT": "solana",
        }
    )

    def __init__(self, client: httpx.AsyncClient, *, api_key: str = "") -> None:
        self._client = client
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "coingecko"

    def supports(self, symbol: str) -> bool:
        return symbol in self.COIN_IDENTIFIERS

    async def daily_close(self, symbol: str, period: TimeRange) -> pd.Series:
        """取日收盤參考價，index 是 UTC 日期。"""
        coin_identifier = self.COIN_IDENTIFIERS[symbol]
        response = await self._client.get(
            f"{self.BASE_URL}/coins/{coin_identifier}/market_chart/range",
            params={
                "vs_currency": "usd",
                "from": int(period.start.timestamp()),
                "to": int(period.end.timestamp()),
            },
            headers={"x-cg-demo-api-key": self._api_key} if self._api_key else {},
        )
        response.raise_for_status()

        prices = pd.DataFrame(
            response.json()["prices"], columns=["epoch_milliseconds", "price"]
        )
        moments = pd.to_datetime(prices["epoch_milliseconds"], unit="ms", utc=True)
        return (
            pd.Series(prices["price"].to_numpy(), index=moments)
            .resample("1D")
            .last()
            .rename("theirs")
        )
