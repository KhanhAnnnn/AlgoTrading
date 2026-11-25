-- ============================================================
-- ddl_crypto_deterministic_test.sql - Isolated Flink Test Pipeline
-- Reads from isolated test topics: test-crypto-bars-1m, test-crypto-news
-- Sinks into: test-crypto-signals
-- Zero impact on production topics (crypto-bars-1m, crypto-news, crypto-signals)
-- ============================================================

CREATE OR REPLACE TABLE test_crypto_bars (
    asset_type VARCHAR,
    symbol VARCHAR,
    `source` VARCHAR,
    `open` FLOAT,
    high FLOAT,
    low FLOAT,
    `close` FLOAT,
    volume DECIMAL,
    trade_count FLOAT,
    vwap DECIMAL,
    timestamp_ms BIGINT,
    is_final BOOLEAN,
    event_time AS TO_TIMESTAMP_LTZ(timestamp_ms, 3),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'test-crypto-bars-1m',
    'properties.bootstrap.servers' = 'redpanda-1:29092,redpanda-2:29093',
    'properties.group.id' = 'test-crypto-bars-group',
    'properties.auto.offset.reset' = 'earliest',
    'format' = 'json'
);

CREATE OR REPLACE TABLE test_crypto_news (
    asset_type VARCHAR,
    symbol VARCHAR,
    `source` VARCHAR,
    id BIGINT,
    headline VARCHAR,
    summary VARCHAR,
    sentiment DECIMAL,
    timestamp_ms BIGINT,
    event_time AS TO_TIMESTAMP_LTZ(timestamp_ms, 3),
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'test-crypto-news',
    'properties.bootstrap.servers' = 'redpanda-1:29092,redpanda-2:29093',
    'properties.group.id' = 'test-crypto-news-group',
    'properties.auto.offset.reset' = 'earliest',
    'format' = 'json'
);

CREATE OR REPLACE TABLE test_crypto_signals_sink (
    asset_type STRING,
    symbol STRING,
    signal_time TIMESTAMP_LTZ,
    signal STRING,
    price FLOAT,
    sentiment DECIMAL,
    sma_20 FLOAT,
    sma_50 FLOAT
) WITH (
    'connector' = 'kafka',
    'topic' = 'test-crypto-signals',
    'properties.bootstrap.servers' = 'redpanda-1:29092,redpanda-2:29093',
    'properties.group.id' = 'test-crypto-signals-sink-group',
    'format' = 'json'
);

CREATE OR REPLACE VIEW test_crypto_sma_20 AS
SELECT symbol, `close`, event_time,
    AVG(`close`) OVER (
        PARTITION BY symbol
        ORDER BY event_time
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS sma_20
FROM test_crypto_bars
WHERE is_final = TRUE;

CREATE OR REPLACE VIEW test_crypto_sma_50 AS
SELECT symbol, `close`, event_time,
    AVG(`close`) OVER (
        PARTITION BY symbol
        ORDER BY event_time
        ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
    ) AS sma_50
FROM test_crypto_bars
WHERE is_final = TRUE;

CREATE OR REPLACE VIEW test_crypto_price_with_movavg AS
SELECT
    s20.symbol,
    s20.`close`,
    s20.event_time,
    CAST(s20.sma_20 AS FLOAT) AS sma_20,
    CAST(s50.sma_50 AS FLOAT) AS sma_50
FROM test_crypto_sma_20 s20
JOIN test_crypto_sma_50 s50
    ON s20.symbol = s50.symbol AND s20.event_time = s50.event_time;

CREATE OR REPLACE VIEW test_crypto_news_and_prices AS
SELECT
    n.symbol,
    n.headline,
    n.sentiment,
    p.`close`,
    p.sma_20,
    p.sma_50,
    n.event_time AS news_time,
    p.event_time AS price_time
FROM test_crypto_news n
JOIN test_crypto_price_with_movavg p
    ON n.symbol = p.symbol
    AND n.event_time BETWEEN p.event_time - INTERVAL '2' MINUTE AND p.event_time + INTERVAL '2' MINUTE;

CREATE OR REPLACE VIEW test_crypto_trading_signals AS
SELECT
    'crypto' AS asset_type,
    symbol,
    news_time AS signal_time,
    `close` AS price,
    sentiment,
    sma_20,
    sma_50,
    CASE
        WHEN sentiment > 0 AND `close` < sma_20
            AND FIRST_VALUE(`close`) OVER (
                PARTITION BY symbol ORDER BY news_time
                ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
            ) >= sma_20 THEN 'BUY'
        WHEN sentiment < 0 AND `close` > sma_20
            AND FIRST_VALUE(`close`) OVER (
                PARTITION BY symbol ORDER BY news_time
                ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
            ) <= sma_20 THEN 'SELL'
        ELSE NULL
    END AS signal
FROM test_crypto_news_and_prices;

INSERT INTO test_crypto_signals_sink
SELECT asset_type, symbol, signal_time, signal, price, sentiment, sma_20, sma_50
FROM test_crypto_trading_signals
WHERE signal IS NOT NULL;
