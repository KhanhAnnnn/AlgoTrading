# PDF vs Source Code Gap Analysis

> **Reference:** `Real-Time Algorithmic Trading_2025May27.pdf` (21 pages)  
> **Repository:** https://github.com/shj37/Algo-Trading-Sentiment-Analysis-Redpanda-Flink  
> **Audit date:** 2026-10-17

---

## GAP 1 — Redpanda Console Broker Address Bug

| | Detail |
|---|---|
| **File** | `docker-compose.yml` line 80 |
| **PDF/Expected** | `redpanda-2` listens on internal port `29093` |
| **Original Code** | `brokers: ["redpanda-1:29092", "redpanda-2:29092"]` — **wrong port for redpanda-2** |
| **Fix Applied** | Changed to `["redpanda-1:29092", "redpanda-2:29093"]` |
| **Impact** | Console could not display redpanda-2 topic partitions or offsets correctly |
| **Status** | ✅ Fixed |

---

## GAP 2 — Trading Signals Sink Broker Address Space

| | Detail |
|---|---|
| **File** | `ddl.sql` line 113 |
| **PDF/Expected** | No space in broker list |
| **Original Code** | `'redpanda-1:29092, redpanda-2:29093'` — leading space after comma |
| **Fix Applied** | Removed space: `'redpanda-1:29092,redpanda-2:29093'` |
| **Impact** | Some Kafka client parsers fail with leading space on broker addresses |
| **Status** | ✅ Fixed |

---

## GAP 3 — `alpaca_config/keys.py` Module Missing

| | Detail |
|---|---|
| **File** | `libs/alpaca_config/keys.py` (did not exist in repo) |
| **PDF/Expected** | All producers and signal-handler import `from alpaca_config.keys import config` |
| **Original Code** | Module not present — all producers would fail with `ModuleNotFoundError` |
| **Fix Applied** | Created `libs/alpaca_config/__init__.py` and `libs/alpaca_config/keys.py` reading from environment variables |
| **Impact** | System cannot start without this file |
| **Status** | ✅ Fixed |

---

## GAP 4 — `signal-handler.py` Hardcoded Author's Windows Path

| | Detail |
|---|---|
| **File** | `signal-handler.py` line 118 |
| **PDF/Expected** | JAR path must match the deployed environment |
| **Original Code** | `env.add_jars("file:///D:/data engineering/streaming/algo_trading_with_sentiment_analysis/libs/flink-sql-connector-kafka-3.1.0-1.18.jar")` |
| **Issue 1** | Path points to author's local machine — does not exist on any other system |
| **Issue 2** | Uses JAR version `3.1.0-1.18` but `libs/` only contains `3.1.0-1.18.jar` (different from Dockerfile which uses `3.2.0-1.19`) |
| **Issue 3** | Uses PyFlink (`from pyflink...`) which is not in `requirements.txt` and is extremely heavy |
| **Fix Applied** | Rewrote `signal-handler.py` to use `kafka-python` (already in requirements.txt) as a pure consumer, eliminating PyFlink dependency entirely. Added DRY_RUN mode for safety. |
| **Impact** | Critical — signal handler would fail to import on any machine |
| **Status** | ✅ Fixed |

---

## GAP 5 — `news-producer.py` Uses Deprecated `alpaca-trade-api` SDK

| | Detail |
|---|---|
| **File** | `news-producer.py` lines 4-5, `requirements.txt` line 1 |
| **PDF/Expected** | Fetch news from Alpaca API |
| **Original Code** | `from alpaca_trade_api import REST` — uses legacy SDK `alpaca-trade-api==3.2.0` |
| **Issue** | `alpaca-trade-api==3.2.0` requires `PyYAML==6.0.1` which requires C++ Build Tools to compile on Python 3.14 — **build fails** |
| **Fix Applied** | Rewrote `news-producer.py` to use `NewsClient` from `alpaca-py==0.40.1` (already installed, no C compiler needed) |
| **Status** | ✅ Fixed |

---

## GAP 6 — `sys.path` Missing for `alpaca_config` Module Resolution

| | Detail |
|---|---|
| **File** | `prices-producer.py`, `signal-handler.py` |
| **PDF/Expected** | Scripts run from project root can resolve `libs/alpaca_config` |
| **Original Code** | No `sys.path` manipulation — requires module to be installed or on PYTHONPATH |
| **Fix Applied** | Added `sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))` to all producer scripts |
| **Status** | ✅ Fixed |

---

## GAP 7 — `signal-handler.py` Always Places Orders (No DRY_RUN)

| | Detail |
|---|---|
| **File** | `signal-handler.py` |
| **PDF/Expected** | Safety consideration for paper trading |
| **Original Code** | Any BUY/SELL signal immediately calls `api.submit_order()` with `random.randint(5, 10)` shares |
| **Risk** | Accidental live trading if wrong credentials provided |
| **Fix Applied** | Added `TRADING_MODE` env var (`DRY_RUN` default, `PAPER_TRADING` opt-in). Added safety check that `ALPACA_TRADE_BASE_URL` must contain `paper-api`. Added duplicate signal deduplication. |
| **Status** | ✅ Fixed |

---

## GAP 8 — `ddl.sql` Contains `SELECT *` and diagnostic statements

| | Detail |
|---|---|
| **File** | `ddl.sql` lines 23, 47, 49, 51 |
| **SQL** | `SELECT * FROM market_news;`, `SELECT * FROM stock_prices;`, `SHOW TABLES;`, `DESCRIBE market_news;` |
| **Issue** | These diagnostic queries will start streaming jobs if run as a batch via `SOURCE` in SQL client; they will block or run indefinitely |
| **Recommendation** | Remove or comment out these lines when running in production. Keep them only for interactive debugging sessions. |
| **Status** | ⚠️ Documented — no auto-fix applied to preserve original logic |

---

## GAP 9 — `trading_signals` View Schema Mismatch with Sink Table

| | Detail |
|---|---|
| **File** | `ddl.sql` lines 93-104 vs 106-116 |
| **Issue** | `trading_signals` view selects `close` and `quantity` (1) but `trading_signals_sink` table only has columns `symbol`, `signal_time`, `signal` |
| **INSERT statement** | `SELECT symbol, news_time, signal FROM trading_signals` — correctly drops `close` and `quantity` |
| **Status** | ✅ No issue — INSERT correctly selects only the 3 needed columns |

---

## GAP 10 — `sma_50` Computed But Not Used in Signal Logic

| | Detail |
|---|---|
| **File** | `ddl.sql` lines 58-64, 99-103 |
| **PDF** | SMA-50 is mentioned as part of the strategy |
| **Code** | `sma_50` view is created and joined in `price_with_movavg`, but `trading_signals` CASE only references `sma_20` |
| **Status** | ⚠️ Strategy gap — `sma_50` has no effect on BUY/SELL decisions. This appears intentional per PDF description (uses SMA-20 crossover as the primary signal) |

---

## GAP 11 — Flink LAG() Not Supported in Streaming Mode

| | Detail |
|---|---|
| **File** | `ddl.sql` lines 100-101 |
| **Code** | `LAG(\`close\`, 1) OVER (PARTITION BY symbol ORDER BY news_time)` |
| **Issue** | Apache Flink does NOT support `LAG()` window function in streaming mode. `LAG()` is a batch-only operation in Flink SQL. |
| **Impact** | The `trading_signals` view will fail with a validation error when executed as a streaming job |
| **Recommendation** | Replace `LAG()` with a stateful approach: use `LAST_VALUE()` over a time window, or use `ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING` with a bounded over window, or join the stream with itself offset by 1 row |
| **Status** | ⚠️ Critical known issue — requires architectural change to the SQL |

---

## Summary Table

| # | Gap | Severity | Status |
|---|---|---|---|
| 1 | Redpanda Console wrong port | Medium | ✅ Fixed |
| 2 | Broker address space in DDL | Low | ✅ Fixed |
| 3 | `alpaca_config` module missing | Critical | ✅ Fixed |
| 4 | Hardcoded author path in signal-handler | Critical | ✅ Fixed |
| 5 | `alpaca-trade-api` fails to build on Python 3.14 | High | ✅ Fixed |
| 6 | `sys.path` missing for module resolution | High | ✅ Fixed |
| 7 | No DRY_RUN mode in signal-handler | High | ✅ Fixed |
| 8 | Diagnostic SELECT* in DDL SQL | Low | ⚠️ Documented |
| 9 | Schema mismatch (self-resolving) | Low | ✅ No issue |
| 10 | `sma_50` unused in signal logic | Medium | ⚠️ Documented |
| 11 | `LAG()` unsupported in Flink streaming | Critical | ⚠️ Requires DDL fix |
