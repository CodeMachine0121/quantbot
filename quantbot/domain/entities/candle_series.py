# quantbot/domain/entities/candle_series.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.candle_columns import CandleColumns
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe


class CandleSeries:
    """一段 K 線，以及它自己知道怎麼做的那些事。

    直接傳 DataFrame 也能跑，但「重疊時誰說了算」「哪一根還沒收完」「切片的
    邊界含不含端點」這些規則就會散到每個呼叫端各寫一次，而它們每一條都是
    安靜出錯的那種。所以它們是這個類別的方法。
    """

    def __init__(self, instrument: Instrument, candles: pd.DataFrame) -> None:
        self.instrument = instrument
        self._candles = CandleColumns.conform(candles)

    @classmethod
    def empty(cls, instrument: Instrument) -> CandleSeries:
        index = pd.DatetimeIndex([], tz="UTC", name=CandleColumns.OPEN_TIME)
        return cls(instrument, pd.DataFrame(index=index))

    @property
    def frame(self) -> pd.DataFrame:
        """底層的 DataFrame。指標與圖表吃這個。"""
        return self._candles

    @property
    def open_times(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self._candles.index)

    def __len__(self) -> int:
        return len(self._candles)

    def is_empty(self) -> bool:
        return self._candles.empty

    def merge(self, other: CandleSeries) -> CandleSeries:
        """併入另一段。**重疊時以 self 為準**。

        呼叫端因此可以用順序表達權威性：批次檔是定稿、REST 是暫時的，
        所以寫 archive.merge(rest)，而不是反過來。
        """
        if other.instrument != self.instrument:
            raise ValueError(
                f"不同的 instrument 不可合併：{self.instrument} / {other.instrument}"
            )
        # 先去重再排序，順序不能倒過來：sort_index() 預設是 quicksort，**不穩定**，
        # 同一個時間戳的兩列誰留下來會變成隨機的。concat 的順序是確定的，
        # 所以在還沒排序的表上 keep="first"，self 才真的勝出。
        combined = pd.concat([self._candles, other.frame])
        return CandleSeries(
            self.instrument, combined[~combined.index.duplicated(keep="first")]
        )

    def restricted_to(self, period: TimeRange) -> CandleSeries:
        """切出 [start, end) 這段。右端開區間，跟 TimeRange 的語意一致。"""
        index = self.open_times
        selected = (index >= period.start) & (index < period.end)
        return CandleSeries(self.instrument, self._candles.loc[selected])

    def closed_only(self, now: pd.Timestamp) -> CandleSeries:
        """丟掉還沒收完的那一根。

        Day 02 講過最後一根 K 線是進行式；它一旦入庫，
        ON CONFLICT DO NOTHING 就再也不會更新它了。
        """
        latest = self.instrument.timeframe.latest_closed_open_time(now)
        return CandleSeries(self.instrument, self._candles.loc[:latest])

    def resample(self, timeframe: Timeframe) -> CandleSeries:
        """聚合成更粗的粒度。交易所產生日線的方式就是這樣。

        五個欄位的規則各不相同，寫錯不會報錯、圖也畫得出來，所以這段只寫一次，
        放在 K 線自己身上。label="left" 是因為索引存的是開盤時間。
        """
        aggregated = self._candles.resample(
            timeframe.pandas_frequency, label="left", closed="left"
        ).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            quote_volume=("quote_volume", "sum"),
            taker_buy_base_volume=("taker_buy_base_volume", "sum"),
            taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
            trade_count=("trade_count", "sum"),
        )
        coarser = Instrument(
            symbol=self.instrument.symbol,
            market=self.instrument.market,
            timeframe=timeframe,
        )
        return CandleSeries(coarser, aggregated.dropna(subset=["open"]))

    def with_identity_columns(self) -> pd.DataFrame:
        """加上 symbol 與 market 欄，給落地用。"""
        labelled = self._candles.copy()
        labelled["symbol"] = self.instrument.symbol
        labelled["market"] = str(self.instrument.market)
        return labelled
