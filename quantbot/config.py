from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    postgres_dsn: str = "postgresql://quantbot:changeme@localhost:5432/market"

    coingecko_api_key: str = ""  # 對照組用，可留空走匿名額度
    raw_data_directory: Path = Path("data/raw")

    default_symbol: str = "BTCUSDT"
    default_market: str = "spot"


settings = Settings()
