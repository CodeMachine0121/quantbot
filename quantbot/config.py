from dataclasses import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/market"

    default_symbol: str = "BTCUSDT"
    default_market: str = "spot"

settings = Settings()
