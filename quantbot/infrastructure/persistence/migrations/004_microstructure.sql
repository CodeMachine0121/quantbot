-- quantbot/infrastructure/persistence/migrations/004_microstructure.sql
-- 逐筆成交。主鍵刻意不含 transact_time：同一個時間戳有幾十筆成交是常態，
-- 唯一的東西是 trade_id。時間只負責分區與查詢。
CREATE TABLE IF NOT EXISTS agg_trades (
    symbol          TEXT             NOT NULL,   -- 'BTC/USDT'
    market          TEXT             NOT NULL,   -- 'spot' | 'usdm'
    trade_id        BIGINT           NOT NULL,   -- 聚合成交編號，唯一鍵
    transact_time   TIMESTAMPTZ      NOT NULL,   -- 成交時間，UTC
    price           DOUBLE PRECISION NOT NULL,
    quantity        DOUBLE PRECISION NOT NULL,   -- 以基礎幣計價
    first_trade_id  BIGINT           NOT NULL,   -- 這一列併了哪幾筆原始成交
    last_trade_id   BIGINT           NOT NULL,
    buyer_is_maker  BOOLEAN          NOT NULL,   -- 買方掛單 → 主動方是賣方
    source          TEXT             NOT NULL,   -- 'binance_archive' | 'binance_websocket'
    ingested_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT agg_trades_pkey PRIMARY KEY (symbol, market, transact_time, trade_id)
);

-- hypertable 的分區欄必須是主鍵的一部分，所以 transact_time 在主鍵裡；
-- 真正防重複的是 trade_id，但單獨對它建唯一索引在分區表上做不到，
-- 所以複合主鍵是 (symbol, market, transact_time, trade_id)。
-- 這代表「同一筆成交用不同的時間戳寫兩次」擋不住——而那不會發生：
-- 時間戳是交易所給的事實，不是我們算出來的。
SELECT create_hypertable(
    'agg_trades',
    by_range('transact_time', INTERVAL '1 day'),
    if_not_exists => TRUE
);

-- chunk 只有一天，因為一天就是七十幾萬列。K 線那張表七天一個 chunk，
-- 是因為一年的 1 分鐘 K 線才五十幾萬列——同樣的資料量，時間跨度差 2500 倍。
CREATE INDEX IF NOT EXISTS agg_trades_trade_id_index
    ON agg_trades (symbol, market, trade_id DESC);

-- 掛單簿深度摘要。這張表的欄位就是 DepthColumns.LEVELS 的樣子：
-- 錄下來的是前 5／10／20 檔的加總，事後 NEVER 算得出前 7 檔。
CREATE TABLE IF NOT EXISTS order_book_depth (
    symbol          TEXT             NOT NULL,
    market          TEXT             NOT NULL,
    captured_at     TIMESTAMPTZ      NOT NULL,
    best_bid_price  DOUBLE PRECISION NOT NULL,
    best_ask_price  DOUBLE PRECISION NOT NULL,
    bid_quantity_5  DOUBLE PRECISION NOT NULL,
    ask_quantity_5  DOUBLE PRECISION NOT NULL,
    bid_quantity_10 DOUBLE PRECISION NOT NULL,
    ask_quantity_10 DOUBLE PRECISION NOT NULL,
    bid_quantity_20 DOUBLE PRECISION NOT NULL,
    ask_quantity_20 DOUBLE PRECISION NOT NULL,
    ingested_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT order_book_depth_pkey PRIMARY KEY (symbol, market, captured_at)
);

SELECT create_hypertable(
    'order_book_depth',
    by_range('captured_at', INTERVAL '1 day'),
    if_not_exists => TRUE
);

ALTER TABLE agg_trades SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, market',
    timescaledb.compress_orderby   = 'transact_time DESC, trade_id DESC'
);

ALTER TABLE order_book_depth SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, market',
    timescaledb.compress_orderby   = 'captured_at DESC'
);

-- 7 天就壓，比 K 線那張表的 30 天積極得多：逐筆成交長得太快，
-- 而且不會被回補改寫——歷史的成交是定稿，補洞只會往後加。
SELECT add_compression_policy('agg_trades', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('order_book_depth', INTERVAL '7 days', if_not_exists => TRUE);
