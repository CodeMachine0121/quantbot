-- quantbot/infrastructure/persistence/migrations/003_compression.sql
-- compress_segmentby 放查詢時的等值條件欄位，壓縮後才能只解壓需要的那幾段；
-- compress_orderby 放時間，讓同一段內的時間戳連續，delta-of-delta 才壓得下去。
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, market, timeframe',
    timescaledb.compress_orderby   = 'open_time DESC'
);

-- 30 天的門檻是緩衝：最近一個月的資料還可能被 Day 08 的管線回補，
-- 壓縮過的 chunk 回填會麻煩很多。
SELECT add_compression_policy('candles', INTERVAL '30 days', if_not_exists => TRUE);
