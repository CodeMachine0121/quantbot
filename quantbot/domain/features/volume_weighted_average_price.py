# quantbot/domain/features/volume_weighted_average_price.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.values.feature_parameters import FeatureParameters
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView
from quantbot.domain.values.price_source import PriceSource
from quantbot.domain.values.vwap_mode import VWAPMode


class VWAP:
    """成交量加權平均價。實作 domain 的 Feature。

        VWAP = Σ(價格 × 成交量) / Σ成交量

    算術平均把成交 1 顆 BTC 跟成交 100 顆當成一樣重要，而市場顯然不是這樣運作的。
    加權之後這條線代表的是「這段期間市場的平均成本」，也因此它跟均線是兩種東西：
    均線問的是價格往哪走，VWAP 問的是**現在的價格對已經進場的人是賺還是賠**。

    這個類別同時負責加權標準差，因為那是同一組加權統計量的第二階，拆開會讓
    「用哪個價格、怎麼累積」這兩個決定被複製兩份。
    """

    def __init__(
        self,
        *,
        mode: VWAPMode = VWAPMode.SESSION,
        window: int = 20,
        price_source: PriceSource = PriceSource.TYPICAL,
    ) -> None:
        if window < 1:
            raise ValueError(f"window 必須 >= 1，收到 {window}")
        self.mode = mode
        self.window = window
        self.price_source = price_source

    @property
    def name(self) -> str:
        if self.mode is VWAPMode.SESSION:
            return "vwap_session"
        return f"vwap_rolling_{self.window}"

    @property
    def warmup_bar_count(self) -> int:
        """滾動模式要滿一個視窗；日內模式不用暖機，但一天的頭幾根很不穩。

        「不穩」跟「還沒有值」是兩件事，所以日內模式回 0——它從第一根就有值，
        只是那個值只用了一根 K 線。把它算成暖機期會讓每天開頭都被切掉，
        而那正是日內 VWAP 最常被使用的時段。
        """
        return self.window - 1 if self.mode is VWAPMode.ROLLING else 0

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        return frozenset({MarketInput.CANDLES})

    def compute(self, view: MarketView) -> pd.Series:
        candles = view.candles.frame
        price = self.price_source.of(candles)
        volume = candles["volume"].astype("float64")
        return self._weighted_mean(price, volume).rename(self.name)

    def standard_deviation(self, view: MarketView) -> pd.Series:
        """加權標準差，用來畫通道、也用來標準化偏離程度。

        算法是「加權平方的平均 − 加權平均的平方」，但**先把價格平移到 0 附近**。
        直接對 BTC 的價格用那條恆等式會出事：價格 65,000 的平方是 4.2e9，而
        變異數可能只有 25，兩個相差八個數量級的數相減會把有效位數吃掉大半
        （float64 只有約 16 位十進位有效位數）。平移之後兩邊的量級就接近了。

        平移不改變變異數——這是變異數的平移不變性，所以這不是近似，是等價變換。
        """
        candles = view.candles.frame
        price = self.price_source.of(candles)
        volume = candles["volume"].astype("float64")

        centre = float(price.mean())
        shifted = price - centre
        mean = self._weighted_mean(shifted, volume)
        mean_of_squares = self._weighted_mean(shifted**2, volume)
        # 浮點誤差可能讓變異數變成 -1e-12 這種值，開根號會得到 NaN
        variance = (mean_of_squares - mean**2).clip(lower=0.0)
        # 用 Series.pow 而不是 np.sqrt：後者的回傳型別在 pandas-stubs 下退化成 Any，
        # 於是 mypy --strict 再也看不出這個函式回傳的是 Series
        return variance.pow(0.5).rename(f"{self.name}_standard_deviation")

    def _weighted_mean(self, values: pd.Series, volume: pd.Series) -> pd.Series:
        """加權平均。兩種累積方式只差 cumsum 與 rolling().sum()。

        分母是成交量的累積和，所以完全沒有成交的那幾根會讓分母是 0。那時候回 NaN
        而不是 0——「沒有人成交」時平均成本沒有定義，填 0 會在圖上畫出一條掉到
        原點的線，而那條線會被下游當成真的價格。
        """
        weighted = values * volume
        if self.mode is VWAPMode.SESSION:
            session = self._session_of(values.index)
            numerator = weighted.groupby(session).cumsum()
            denominator = volume.groupby(session).cumsum()
        else:
            numerator = weighted.rolling(self.window).sum()
            denominator = volume.rolling(self.window).sum()
        return (numerator / denominator).where(denominator > 0)

    @staticmethod
    def _session_of(index: pd.Index) -> pd.Series:
        """哪一天。加密貨幣沒有收盤，所以「一天」是人為切的 UTC 午夜。

        用 normalize() 而不是 index.date：後者會產生 object 型別的 Python date，
        groupby 會慢好幾倍，而且時區資訊在那一步就掉了。
        """
        times = pd.DatetimeIndex(index)
        return pd.Series(times.normalize(), index=index, name="session")


class VWAPBuilder:
    """設定檔的 vwap。mode 決定要不要看 window。"""

    @property
    def kind(self) -> str:
        return "vwap"

    def build(self, parameters: FeatureParameters) -> VWAP:
        return VWAP(
            mode=_vwap_mode(parameters),
            window=parameters.integer("window", 20),
            price_source=_price_source(parameters),
        )


def _vwap_mode(parameters: FeatureParameters) -> VWAPMode:
    """設定檔的字串轉 VWAPMode。錯誤訊息要列出合法值，不然使用者只能猜。

    這兩個 helper 是模組層級的函式，因為它們被同一個檔案的兩個 builder 共用，
    而它們不屬於任何一個物件的行為——它們是設定檔字串到值物件的轉換。
    """
    raw = parameters.text("mode", VWAPMode.SESSION.value)
    if raw not in tuple(VWAPMode):
        raise ValueError(
            f"mode 只能是 {[value.value for value in VWAPMode]}，實得 {raw!r}"
        )
    return VWAPMode(raw)


def _price_source(parameters: FeatureParameters) -> PriceSource:
    raw = parameters.text("price_source", PriceSource.TYPICAL.value)
    if raw not in tuple(PriceSource):
        raise ValueError(
            f"price_source 只能是 {[value.value for value in PriceSource]}，"
            f"實得 {raw!r}"
        )
    return PriceSource(raw)
