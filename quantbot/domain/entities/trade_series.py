# quantbot/domain/entities/trade_series.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.entities.candle_series import CandleSeries
from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.taker_side import TakerSide
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.trade_columns import TradeColumns


class TradeSeries:
    """一段逐筆成交，以及它自己知道怎麼做的那些事。

    跟 CandleSeries 最大的差別是**去重看的不是索引**：同一個時間戳可以有很多筆
    成交，所以重跑批次或串流重連之後，要靠 trade_id 判斷哪些是同一筆。
    這條規則寫錯的症狀很難看出來——成交量會多算，而價格看起來完全正常。
    """

    def __init__(self, listing: Listing, trades: pd.DataFrame) -> None:
        self.listing = listing
        self._trades = TradeColumns.conform(trades).sort_index()

    @classmethod
    def empty(cls, listing: Listing) -> TradeSeries:
        index = pd.DatetimeIndex([], tz="UTC", name=TradeColumns.TRANSACT_TIME)
        frame = pd.DataFrame(index=index)
        for column in TradeColumns.INTEGER_COLUMNS:
            frame[column] = pd.Series(dtype="int64")
        for column in TradeColumns.FLOAT_COLUMNS:
            frame[column] = pd.Series(dtype="float64")
        for column in TradeColumns.BOOLEAN_COLUMNS:
            frame[column] = pd.Series(dtype="bool")
        return cls(listing, frame)

    @property
    def frame(self) -> pd.DataFrame:
        return self._trades

    @property
    def transact_times(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self._trades.index)

    def __len__(self) -> int:
        return len(self._trades)

    def is_empty(self) -> bool:
        return self._trades.empty

    def merge(self, other: TradeSeries) -> TradeSeries:
        """併入另一段，**以 trade_id 去重**，重疊時以 self 為準。

        跟 CandleSeries.merge 一樣先去重再排序：sort_index() 是不穩定排序，
        排完再去重的話留下來的是哪一列會變成隨機的。
        """
        if other.listing != self.listing:
            raise ValueError(
                f"不同的 listing 不可合併：{self.listing} / {other.listing}"
            )
        combined = pd.concat([self._trades, other.frame])
        deduplicated = combined[
            ~combined[TradeColumns.TRADE_ID].duplicated(keep="first")
        ]
        return TradeSeries(self.listing, deduplicated)

    def restricted_to(self, period: TimeRange) -> TradeSeries:
        """切出 [start, end) 這段。右端開區間，跟全專案的慣例一致。"""
        times = self.transact_times
        selected = (times >= period.start) & (times < period.end)
        return TradeSeries(self.listing, self._trades.loc[selected])

    def taker_sides(self) -> pd.Series:
        """每一筆是主動買還是主動賣。轉換只有一份，在 TakerSide 裡。"""
        return self._trades[TradeColumns.BUYER_IS_MAKER].map(
            {True: TakerSide.SELL.value, False: TakerSide.BUY.value}
        )

    def missing_trade_id_count(self) -> int:
        """有幾筆成交沒被涵蓋到。

        aggTrades 的 first/last trade id 應該首尾相接：前一列的 last + 1 等於
        這一列的 first。斷號代表這段資料不完整，而它 NEVER 以缺列的形式表現——
        表看起來是連續的，只是中間少了幾筆成交。
        """
        if len(self._trades) < 2:
            return 0
        first = self._trades[TradeColumns.FIRST_TRADE_ID]
        last = self._trades[TradeColumns.LAST_TRADE_ID]
        breaks = first.to_numpy()[1:] - last.to_numpy()[:-1] - 1
        return int(breaks[breaks > 0].sum())

    def aggregate_to_candles(self, timeframe: Timeframe) -> CandleSeries:
        """把逐筆成交聚合回 K 線。

        這不是為了省下載——官方的 K 線就在那裡。它的用途是**對帳**：拿重建出來的
        K 線跟官方的逐欄比對，如果九個欄位全對得上，就同時證明了欄位對映、時間戳
        單位、時區、聚合邊界、taker 方向這五件事都沒錯。這是這層資料唯一拿得到的
        對照組，因為外面沒有免費的第二個 tick 來源。

        trade_count 用 last - first + 1 加總而不是列數：aggTrades 的一列是被併過的。
        """
        trades = self._trades
        quote_amount = trades[TradeColumns.PRICE] * trades[TradeColumns.QUANTITY]
        taker_buy = ~trades[TradeColumns.BUYER_IS_MAKER]

        working = pd.DataFrame(
            {
                "price": trades[TradeColumns.PRICE],
                "quantity": trades[TradeColumns.QUANTITY],
                "quote_amount": quote_amount,
                "taker_buy_base": trades[TradeColumns.QUANTITY].where(taker_buy, 0.0),
                "taker_buy_quote": quote_amount.where(taker_buy, 0.0),
                "trade_count": (
                    trades[TradeColumns.LAST_TRADE_ID]
                    - trades[TradeColumns.FIRST_TRADE_ID]
                    + 1
                ),
            },
            index=trades.index,
        )
        aggregated = working.resample(
            timeframe.pandas_frequency, label="left", closed="left"
        ).agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            volume=("quantity", "sum"),
            quote_volume=("quote_amount", "sum"),
            taker_buy_base_volume=("taker_buy_base", "sum"),
            taker_buy_quote_volume=("taker_buy_quote", "sum"),
            trade_count=("trade_count", "sum"),
        )
        aggregated.index.name = CandleColumns.OPEN_TIME
        instrument = Instrument(
            symbol=self.listing.symbol,
            market=self.listing.market,
            timeframe=timeframe,
        )
        # 沒有任何成交的那幾格 open 是 NaN。官方 K 線在完全沒成交時也不出這一根，
        # 所以丟掉它才對得起來——補一根「開高低收都等於前收」的假 K 線是捏造資料。
        return CandleSeries(instrument, aggregated.dropna(subset=["open"]))
