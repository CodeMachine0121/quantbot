-- quantbot/infrastructure/persistence/migrations/002_aggregates.sql
-- timeframe 是常數欄位而不是 GROUP BY 的欄位：來源固定是 1m，
-- 但讀出來的東西要能回答「這是 5m」，CandleRepository 才查得到它。
-- GROUP BY 必須寫完整的 time_bucket(...)：寫成輸出別名 open_time 的話，
-- Postgres 會解析成來源欄位，TimescaleDB 會拒絕建立。
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT
    symbol,
    market,
    '5m'::TEXT AS timeframe,
    time_bucket(INTERVAL '5 minutes', open_time) AS open_time,
    first(open, open_time)      AS open,
    max(high)                   AS high,
    min(low)                    AS low,
    last(close, open_time)      AS close,
    sum(volume)                 AS volume,
    sum(trade_count)::INTEGER   AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY symbol, market, time_bucket(INTERVAL '5 minutes', open_time)
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1h
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT
    symbol,
    market,
    '1h'::TEXT AS timeframe,
    time_bucket(INTERVAL '1 hour', open_time) AS open_time,
    first(open, open_time)      AS open,
    max(high)                   AS high,
    min(low)                    AS low,
    last(close, open_time)      AS close,
    sum(volume)                 AS volume,
    sum(trade_count)::INTEGER   AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY symbol, market, time_bucket(INTERVAL '1 hour', open_time)
WITH NO DATA;

CALL refresh_continuous_aggregate('candles_5m', NULL, NULL);
CALL refresh_continuous_aggregate('candles_1h', NULL, NULL);

SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists     => TRUE);

SELECT add_continuous_aggregate_policy('candles_1h',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '2 hours',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists     => TRUE);
