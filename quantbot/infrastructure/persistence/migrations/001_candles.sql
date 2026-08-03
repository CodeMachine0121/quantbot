-- quantbot/infrastructure/persistence/migrations/001_candles.sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS candles (
    symbol      TEXT             NOT NULL,   -- 'BTC/USDT'
    market      TEXT             NOT NULL,   -- 'spot' | 'perp'
    timeframe   TEXT             NOT NULL,   -- '1m' | '1d'
    open_time   TIMESTAMPTZ      NOT NULL,   -- 這根 K 線的「開盤」時間，UTC
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,   -- 成交量，以基礎幣計價
    trade_count INTEGER,                     -- 成交筆數，Day 12 會用到
    source      TEXT             NOT NULL,   -- 'binance_vision' | 'binance_rest'
    ingested_at TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT candles_pkey PRIMARY KEY (symbol, market, timeframe, open_time)
);

SELECT create_hypertable(
    'candles',
    by_range('open_time', INTERVAL '7 days'),
    if_not_exists => TRUE
);
