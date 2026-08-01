import io
import zipfile

import httpx
import pandas as pd


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

# 官方 CSV 沒有標頭列，欄位順序寫死在這裡，來源是 Binance public data 文件。
RAW_COLUMNS: list[str] = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]

FLOAT_COLUMNS: list[str] = ["open", "high", "low", "close", "volume", "quote_volume"]

# Binance 的 timeframe 字串跟 pandas 的 freq 字串不一樣，要對映，不要直接傳。
# pandas 的 "1m" 不是分鐘，"1min" 才是。
PANDAS_FREQ: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}

def detect_epoch_unit(epochs: pd.Series) -> str:
    """用數量級判斷 epoch 整數的時間單位，NEVER 寫死。"""
    magnitude = int(epochs.max())
    if magnitude < 10 ** 11:
        return "s"
    if magnitude < 10 ** 14:
        return "ms"
    return "us"

def download_monthly_klines(symbol: str, timeframe: str, month: str) -> pd.DataFrame:
    """下載單一月份的現貨 K 線 zip，回傳未經轉換的原始欄位。

    Args:
        symbol: 交易所格式的現貨交易對，例如 "BTCUSDT"。
        timeframe: K 線的時間框架，例如 "1d"、"1h"、"1m"。
        month: 月份，格式 "YYYY-MM"。
    """
    url = f"{BASE_URL}/{symbol}/{timeframe}/{symbol}-{timeframe}-{month}.zip"
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        csv_bytes = archive.read(archive.namelist()[0])
    return pd.read_csv(
        io.BytesIO(csv_bytes), header=None, names=RAW_COLUMNS, dtype=str
    )

def normalize_klines(raw: pd.DataFrame) -> pd.DataFrame:
    """把原始欄位轉成統一 schema：UTC 的 DatetimeIndex ＋ float64 的 OHLCV。"""
    open_time = pd.to_numeric(raw["open_time"])
    close_time = pd.to_numeric(raw["close_time"])
    unit = detect_epoch_unit(open_time)

    frame = raw[FLOAT_COLUMNS].astype("float64")
    frame["trade_count"] = pd.to_numeric(raw["trade_count"])
    frame["close_time"] = pd.to_datetime(close_time, unit=unit, utc=True)
    frame.index = pd.to_datetime(open_time, unit=unit, utc=True)
    frame.index.name = "open_time"
    return frame.sort_index()

def drop_unclosed_bar(frame: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """丟掉還沒收完的最後一根 K 線。"""
    current_time = now if now is not None else pd.Timestamp.now(tz="UTC")
    return frame.loc[frame["close_time"] <= current_time]


def find_gaps(frame: pd.DataFrame, freq: str) -> pd.DataFrame:
    """回傳預期存在、但資料裡沒有的 K 線起始時間。"""
    expected = pd.date_range(frame.index[0], frame.index[-1], freq=freq, tz="UTC")
    return expected.difference(frame.index)

def load_klines(symbol: str, timeframe: str, months: list[str]) -> pd.DataFrame:
    """下載多個月份並接成一張表：排序、去重、丟掉未收完的那一根。"""
    monthly = [
        normalize_klines(download_monthly_klines(symbol, timeframe, month))
        for month in months
    ]

    combined = pd.concat(monthly).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]

    return drop_unclosed_bar(combined)

def resample_ohlcv(frame: pd.DataFrame, freq: str) -> pd.DataFrame:
    """把細粒度 K 線聚合成粗粒度，交易所產生日線的方式就是這樣。"""
    aggregated = frame.resample(freq, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        trade_count=("trade_count", "sum"),
    )
    return aggregated.dropna(subset=["open"])
