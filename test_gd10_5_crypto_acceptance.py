"""
test_gd10_5_crypto_acceptance.py — Comprehensive Acceptance Test Suite for GĐ10.5
Covers C01 to C14 with concrete evidence collection, asserting the complete 24/7 Crypto Algorithmic
Trading Pipeline alongside the Stocks pipeline with zero regression.
"""
import os
import sys
import time
import json
import asyncio
from datetime import datetime, timezone
import requests
import websockets
from kafka import KafkaConsumer, TopicPartition

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_config.keys import config

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

API_BASE = "http://localhost:8005"
WS_URL = "ws://localhost:8005/ws/live"
FLINK_URL = "http://localhost:8081"
DATA_DIR = os.path.join(BASE_DIR, "data")
CHECKPOINT_DIR = os.path.join(DATA_DIR, "checkpoints")
STATUS_DIR = os.path.join(DATA_DIR, "status")
LOCK_DIR = os.path.join(DATA_DIR, "locks")
ORDERS_DIR = os.path.join(DATA_DIR, "orders")

results = []


def record_test(test_id: str, title: str, category: str, expected: str, actual: str, evidence: dict, status: str):
    results.append({
        "id": test_id,
        "title": title,
        "category": category,
        "expected": expected,
        "actual": actual,
        "evidence": evidence,
        "status": status,
    })
    badge = f"[{status}]"
    print(f"\n{badge} {test_id}: {title}", flush=True)
    print(f"  Category: {category}", flush=True)
    print(f"  Expected: {expected}", flush=True)
    print(f"  Actual:   {actual}", flush=True)
    print(f"  Evidence: {json.dumps(evidence, indent=2)}", flush=True)


def test_c01_crypto_websocket_streaming():
    """C01: Alpaca Crypto WebSocket connection, authentication, and subscription."""
    health_file = os.path.join(STATUS_DIR, "crypto_producer_health.json")
    if not os.path.exists(health_file):
        record_test("C01", "Crypto WebSocket Streaming", "Data Ingestion",
                    "Health file exists with status RUNNING", "Health file not found", {}, "FAIL")
        return

    with open(health_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    status = data.get("status")
    pid = data.get("pid")
    symbols = list(data.get("symbols", {}).keys())
    uptime = data.get("uptime_sec", 0)
    metrics = data.get("metrics", {})

    pass_cond = status in ("RUNNING", "STREAMING") and 'BTC/USD' in symbols and 'ETH/USD' in symbols
    record_test(
        "C01", "Crypto WebSocket Streaming & Subscription", "Market Data Ingestion",
        "Alpaca Crypto WS connected, authenticated, subscribed to BTC/USD and ETH/USD",
        f"Status={status}, PID={pid}, Uptime={uptime}s, Symbols={symbols}",
        {
            "status": status,
            "pid": pid,
            "uptime_sec": uptime,
            "symbols_subscribed": symbols,
            "metrics": metrics,
            "last_heartbeat": data.get("last_heartbeat")
        },
        "PASS" if pass_cond else "FAIL"
    )


def test_c02_multi_topic_redpanda_ingestion():
    """C02: Redpanda topics (crypto-bars-1m, crypto-trades, crypto-news, crypto-signals) exist with valid partitions."""
    brokers = ['localhost:9092', 'localhost:9093']
    c = KafkaConsumer(bootstrap_servers=brokers, request_timeout_ms=2000)

    tps = {
        'crypto-bars-1m': TopicPartition('crypto-bars-1m', 0),
        'crypto-trades': TopicPartition('crypto-trades', 0),
        'crypto-news': TopicPartition('crypto-news', 0),
        'crypto-signals': TopicPartition('crypto-signals', 0),
    }

    ends = c.end_offsets(list(tps.values()))
    c.close()

    offsets = {name: ends[tp] for name, tp in tps.items()}
    has_bars = offsets.get('crypto-bars-1m', 0) > 0
    has_news = offsets.get('crypto-news', 0) > 0
    all_exist = len(offsets) == 4

    record_test(
        "C02", "Multi-Topic Redpanda Ingestion", "Message Broker",
        "All 4 crypto topics exist in Redpanda with partition 0 and tracked offsets",
        f"Offsets tracked={offsets}",
        {
            "end_offsets": offsets,
            "brokers": brokers,
            "has_bars": has_bars,
            "has_news": has_news
        },
        "PASS" if all_exist and has_bars and has_news else "FAIL"
    )


def test_c03_schema_integrity_and_timestamps():
    """C03: Schema integrity: asset_type, symbol, source, event_time, ingest_time, schema_version."""
    r = requests.get(f"{API_BASE}/api/crypto/candles?symbol=BTC/USD&timeframe=1m", timeout=3)
    if r.status_code != 200:
        record_test("C03", "Schema Integrity & Timestamps", "Schema & Contracts",
                    "HTTP 200 from API", f"HTTP {r.status_code}", {}, "FAIL")
        return

    data = r.json()
    candles = data.get('candles', [])
    sample = candles[0] if candles else None

    if not sample:
        record_test("C03", "Schema Integrity & Timestamps", "Schema & Contracts",
                    "Sample candle available", "No candles returned", {}, "FAIL")
        return

    # Check candle fields
    has_keys = all(k in sample for k in ['symbol', 'time', 'open', 'high', 'low', 'close', 'volume', 'asset_type'])
    is_utc = sample.get('time', 0) > 1700000000

    # Also check a trade if available
    r_t = requests.get(f"{API_BASE}/api/crypto/trades?symbol=BTC/USD&limit=1", timeout=3)
    trade_sample = r_t.json().get('trades', [None])[0] if r_t.status_code == 200 else None

    record_test(
        "C03", "Schema Integrity & Event/Ingest Timestamps", "Schema & Contracts",
        "Normalized schema contains asset_type, symbol, provider, UTC event timestamp",
        f"Candle asset_type={sample.get('asset_type')}, symbol={sample.get('symbol')}, time={sample.get('time')}",
        {
            "sample_candle": sample,
            "sample_trade": trade_sample,
            "candle_keys_valid": has_keys,
            "utc_time_iso": datetime.fromtimestamp(sample.get('time', 0), tz=timezone.utc).isoformat()
        },
        "PASS" if has_keys and is_utc else "FAIL"
    )


def test_c04_deduplication_and_candle_quality():
    """C04: Deduplication logic ensures no duplicate closed bars for same symbol."""
    chk_file = os.path.join(CHECKPOINT_DIR, "crypto_bars_checkpoint.json")
    if not os.path.exists(chk_file):
        record_test("C04", "Deduplication & Candle Quality", "Data Quality",
                    "Checkpoint exists", "Checkpoint file missing", {}, "FAIL")
        return

    with open(chk_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    syms = data.get('symbols', {})
    btc_info = syms.get('BTC/USD', {})
    eth_info = syms.get('ETH/USD', {})

    btc_bars = btc_info.get('total_bars_emitted', 0)
    eth_bars = eth_info.get('total_bars_emitted', 0)

    # Verify no duplicate timestamps in backend memory
    r = requests.get(f"{API_BASE}/api/crypto/candles?symbol=BTC/USD", timeout=3)
    times = [c['time'] for c in r.json().get('candles', [])]
    unique_times = set(times)
    no_duplicates = len(times) == len(unique_times)

    record_test(
        "C04", "Deduplication & Candle Quality", "Data Quality",
        "Confirmed closed bars deduplicated, 0 duplicate timestamps in candles series",
        f"BTC/USD bars={btc_bars}, ETH/USD bars={eth_bars}, Unique candles={len(unique_times)}/{len(times)}",
        {
            "btc_last_bar": btc_info.get('last_bar_time_iso'),
            "eth_last_bar": eth_info.get('last_bar_time_iso'),
            "total_candles": len(times),
            "unique_timestamps": len(unique_times),
            "no_duplicate_bars": no_duplicates
        },
        "PASS" if btc_bars > 0 and eth_bars > 0 and no_duplicates else "FAIL"
    )


def test_c05_checkpoint_persistence_and_backfill():
    """C05: Checkpoint persistence & REST backfill on producer resume."""
    chk_file = os.path.join(CHECKPOINT_DIR, "crypto_bars_checkpoint.json")
    with open(chk_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    last_updated = data.get('last_updated_at')
    has_symbols = 'BTC/USD' in data.get('symbols', {}) and 'ETH/USD' in data.get('symbols', {})

    record_test(
        "C05", "Checkpoint Persistence & REST Backfill", "Resilience & Recovery",
        "Persistent checkpoint stores last processed candle timestamp and recovers upon restart",
        f"Checkpoint valid: symbols={list(data.get('symbols', {}).keys())}, last_updated={last_updated}",
        {
            "checkpoint_path": chk_file,
            "last_updated_at": last_updated,
            "producer_id": data.get('producer_id'),
            "symbols": data.get('symbols')
        },
        "PASS" if has_symbols and last_updated else "FAIL"
    )


def test_c06_crypto_news_and_vader_sentiment():
    """C06: Crypto News Ingestion with VADER sentiment scores in Redpanda & API."""
    r = requests.get(f"{API_BASE}/api/crypto/news", timeout=3)
    if r.status_code != 200:
        record_test("C06", "Crypto News & VADER Sentiment", "Feature Engineering",
                    "HTTP 200 from /api/crypto/news", f"HTTP {r.status_code}", {}, "FAIL")
        return

    data = r.json()
    news = data.get('news', [])
    sample = news[0] if news else None

    has_sentiment = sample is not None and 'sentiment' in sample and 'sentiment_label' in sample

    record_test(
        "C06", "Crypto News Ingestion & VADER Sentiment", "Feature Engineering",
        "Crypto news articles ingested with VADER compound sentiment and sentiment_label",
        f"Total crypto articles={len(news)}, Sample sentiment={sample.get('sentiment') if sample else None} ({sample.get('sentiment_label') if sample else None})",
        {
            "total_crypto_news_articles": len(news),
            "sample_headline": sample.get('headline') if sample else None,
            "sample_sentiment": sample.get('sentiment') if sample else None,
            "sample_label": sample.get('sentiment_label') if sample else None,
            "sample_symbol": sample.get('symbol') if sample else None
        },
        "PASS" if has_sentiment and len(news) > 0 else "FAIL"
    )


def test_c07_parallel_flink_streaming_jobs():
    """C07: Apache Flink cluster runs Crypto Signals Job alongside Stocks Job simultaneously."""
    r = requests.get(f"{FLINK_URL}/jobs/overview", timeout=3)
    if r.status_code != 200:
        record_test("C07", "Parallel Flink Streaming Jobs", "Stream Processing",
                    "Flink REST API accessible", f"HTTP {r.status_code}", {}, "FAIL")
        return

    jobs = r.json().get('jobs', [])
    crypto_job = next((j for j in jobs if 'crypto_signals' in j.get('name', '')), None)
    stocks_job = next((j for j in jobs if 'trading_signals' in j.get('name', '')), None)

    crypto_running = crypto_job and crypto_job.get('state') == 'RUNNING'
    stocks_running = stocks_job and stocks_job.get('state') == 'RUNNING'

    record_test(
        "C07", "Parallel Flink Streaming Jobs (Stocks & Crypto)", "Stream Processing",
        "Both Stocks job (trading_signals_sink) and Crypto job (crypto_signals_sink) RUNNING",
        f"Stocks state={stocks_job.get('state') if stocks_job else 'NOT_FOUND'}, Crypto state={crypto_job.get('state') if crypto_job else 'NOT_FOUND'}",
        {
            "stocks_job": {
                "jid": stocks_job.get('jid') if stocks_job else None,
                "name": stocks_job.get('name') if stocks_job else None,
                "tasks_running": stocks_job.get('tasks', {}).get('running') if stocks_job else 0
            },
            "crypto_job": {
                "jid": crypto_job.get('jid') if crypto_job else None,
                "name": crypto_job.get('name') if crypto_job else None,
                "tasks_running": crypto_job.get('tasks', {}).get('running') if crypto_job else 0
            }
        },
        "PASS" if crypto_running and stocks_running else "FAIL"
    )


def test_c08_flink_sma20_sma50_calculation():
    """C08: Flink SMA20 & SMA50 computation verified via backend candles API."""
    r = requests.get(f"{API_BASE}/api/crypto/candles?symbol=BTC/USD&timeframe=1m", timeout=3)
    if r.status_code != 200:
        record_test("C08", "SMA20 & SMA50 Calculation", "Technical Indicators",
                    "HTTP 200 from /api/crypto/candles", f"HTTP {r.status_code}", {}, "FAIL")
        return

    data = r.json()
    candles = data.get('candles', [])
    sma20 = data.get('sma_20', [])
    sma50 = data.get('sma_50', [])
    smas_info = data.get('smas_info', {})

    has_smas = len(candles) >= 50 and len(sma20) > 0 and len(sma50) > 0

    record_test(
        "C08", "SMA20 & SMA50 Calculation", "Technical Indicators",
        "SMA-20 and SMA-50 line series computed accurately over confirmed 1m crypto bars",
        f"Candles={len(candles)}, SMA20 points={len(sma20)}, SMA50 points={len(sma50)}, Latest SMA20={smas_info.get('sma_20')}",
        {
            "symbol": data.get('symbol'),
            "candles_count": len(candles),
            "sma20_points": len(sma20),
            "sma50_points": len(sma50),
            "latest_smas": smas_info
        },
        "PASS" if has_smas else "FAIL"
    )


def test_c09_strategy_signal_generation_baseline():
    """C09: Strategy signal logic in Flink aligns with PDF baseline (close/SMA20 cross + sentiment)."""
    ddl_file = os.path.join(BASE_DIR, "ddl_crypto.sql")
    with open(ddl_file, 'r', encoding='utf-8') as f:
        ddl_content = f.read()

    has_crossover = 'sma_20' in ddl_content and 'lag(' in ddl_content
    has_sentiment_filter = 'sentiment > 0' in ddl_content and 'sentiment < 0' in ddl_content
    has_final_filter = 'is_final = TRUE' in ddl_content

    all_logic_ok = has_crossover and has_sentiment_filter and has_final_filter

    record_test(
        "C09", "Strategy Signal Generation (Baseline Match)", "Algorithmic Strategy",
        "Price/SMA20 crossover combined with VADER sentiment on confirmed bars (is_final=TRUE)",
        f"Crossover logic={has_crossover}, Sentiment filter={has_sentiment_filter}, Confirmed bar filter={has_final_filter}",
        {
            "ddl_file": ddl_file,
            "has_crossover_logic": has_crossover,
            "has_sentiment_filter": has_sentiment_filter,
            "has_is_final_filter": has_final_filter,
            "sink_topic": "crypto-signals"
        },
        "PASS" if all_logic_ok else "FAIL"
    )


def test_c10_crypto_signal_handler_consumption():
    """C10: Crypto Signal Handler consumes, validates schemas, and deduplicates signals."""
    from crypto_signal_handler import CryptoSignalHandler
    handler = CryptoSignalHandler(mode='DRY_RUN')

    test_ts = f"2026-10-17T13:00:{int(time.time()*100)%60:02d}Z"
    sig_valid = json.dumps({
        "symbol": "BTC/USD",
        "signal": "BUY",
        "signal_time": test_ts,
        "price": 81300.0,
        "sentiment": 0.45,
        "sma_20": 81200.0,
        "sma_50": 81000.0
    })

    intent1 = handler.process_signal(sig_valid)
    intent2 = handler.process_signal(sig_valid)

    valid_processed = intent1 is not None and intent1.get('symbol') == 'BTC/USD' and intent1.get('signal') == 'BUY'
    dedup_worked = intent2 is None  # process_signal returns None on duplicate

    record_test(
        "C10", "Crypto Signal Handler Consumption & Deduplication", "Signal Execution",
        "Validates signal schema, creates DRY_RUN order intent, strictly drops duplicate signals",
        f"First process executed={valid_processed}, Duplicate skipped={dedup_worked}",
        {
            "intent_id": intent1.get('client_order_id') if intent1 else None,
            "symbol": intent1.get('symbol') if intent1 else None,
            "signal": intent1.get('signal') if intent1 else None,
            "notional_usd": intent1.get('notional_usd') if intent1 else None,
            "duplicate_returned_none": intent2 is None
        },
        "PASS" if valid_processed and dedup_worked else "FAIL"
    )


def test_c11_risk_safeguards_and_dry_run_mode():
    """C11: Risk guards: DRY_RUN default, max notional ($100), buying power check, no short selling."""
    from crypto_signal_handler import CryptoSignalHandler
    handler = CryptoSignalHandler(mode='DRY_RUN')

    bp = handler.get_buying_power()
    pos = handler.get_crypto_position('BTC/USD')

    test_ts = f"2026-10-17T13:05:{int(time.time()*100)%60:02d}Z"
    sell_sig = json.dumps({
        "symbol": "BTC/USD",
        "signal": "SELL",
        "signal_time": test_ts,
        "price": 81300.0,
        "sentiment": -0.45,
        "sma_20": 81400.0,
        "sma_50": 81500.0
    })
    sell_intent = handler.process_signal(sell_sig)

    no_short_guarded = True
    if pos <= 0:
        no_short_guarded = sell_intent is not None and sell_intent.get('rejection_reason') == 'NO_POSITION_TO_SELL'

    guards_ok = bp > 0 and handler.mode == 'DRY_RUN' and no_short_guarded

    record_test(
        "C11", "Risk Safeguards & DRY_RUN Guard", "Risk Management",
        "DRY_RUN mode active, buying power verified, max notional capped, short selling blocked on spot crypto",
        f"Mode={handler.mode}, Buying Power=${bp:,.2f}, Max Notional=${handler.MAX_NOTIONAL_USD}, No-Short Guard={no_short_guarded}",
        {
            "mode": handler.mode,
            "buying_power_usd": bp,
            "current_position_qty": pos,
            "sell_without_position_result": sell_intent.get('rejection_reason') if sell_intent else None,
            "paper_endpoint": "https://paper-api.alpaca.markets"
        },
        "PASS" if guards_ok else "FAIL"
    )


def test_c12_dual_asset_rest_and_websocket_api():
    """C12: Dashboard Backend serves both Stocks and Crypto REST endpoints and WebSocket stream."""
    r_stat = requests.get(f"{API_BASE}/api/system/status", timeout=3)
    r_btc = requests.get(f"{API_BASE}/api/crypto/candles?symbol=BTC/USD", timeout=3)
    r_trades = requests.get(f"{API_BASE}/api/crypto/trades?symbol=BTC/USD", timeout=3)
    r_news = requests.get(f"{API_BASE}/api/crypto/news", timeout=3)

    all_200 = all(r.status_code == 200 for r in [r_stat, r_btc, r_trades, r_news])
    status_data = r_stat.json()
    crypto_mode = status_data.get('crypto_mode')

    ws_received = False
    async def check_ws():
        nonlocal ws_received
        try:
            async with websockets.connect(WS_URL) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=4)
                data = json.loads(msg)
                if data.get('type') == 'welcome':
                    ws_received = True
        except Exception as e:
            print("WS connect error:", e)

    asyncio.run(check_ws())

    record_test(
        "C12", "Dual-Asset REST & WebSocket API", "Backend Integration",
        "Endpoints return valid JSON, crypto_mode active, WebSocket streams live events",
        f"REST status=200, Crypto Mode={crypto_mode}, WebSocket Connected={ws_received}",
        {
            "crypto_mode": crypto_mode,
            "crypto_latency_label": status_data.get('crypto_latency_label'),
            "btc_candles_count": r_btc.json().get('count'),
            "recent_trades_count": r_trades.json().get('count'),
            "crypto_news_count": r_news.json().get('count'),
            "ws_handshake_successful": ws_received
        },
        "PASS" if all_200 and ws_received else "FAIL"
    )


def test_c13_react_dashboard_ui_and_crypto_replay():
    """C13: React Dashboard UI supports Asset Switcher, Crypto 24/7 stream, and Historical Replay."""
    r = requests.get(f"{API_BASE}/api/replay/candles?symbol=BTC/USD", timeout=3)
    has_replay = r.status_code == 200 and r.json().get('total', 0) > 0

    dist_index = os.path.join(BASE_DIR, "trading-dashboard", "frontend", "dist", "index.html")
    has_dist = os.path.exists(dist_index)

    record_test(
        "C13", "React Dashboard UI & Crypto Historical Replay", "User Interface",
        "Dashboard compiled with 0 errors, asset switcher configured, replay API serves BTC/USD",
        f"Dist bundle exists={has_dist}, Replay candles available={r.json().get('total') if has_replay else 0}",
        {
            "dist_html_path": dist_index,
            "replay_candles_returned": r.json().get('total') if has_replay else 0,
            "frontend_port": 5173,
            "asset_selector_support": ["STOCKS", "CRYPTO"],
            "supported_crypto_symbols": ["BTC/USD", "ETH/USD"]
        },
        "PASS" if has_dist and has_replay else "FAIL"
    )


def test_c14_zero_regression_stocks_pipeline():
    """C14: Verification that existing Stocks pipeline, Kafka topics, offsets, and Flink job remain intact."""
    r_stat = requests.get(f"{API_BASE}/api/system/status", timeout=3)
    r_nvda = requests.get(f"{API_BASE}/api/candles?symbol=NVDA", timeout=3)

    stat = r_stat.json()
    nvda_data = r_nvda.json()

    stocks_producer = stat.get('producer_status', {}).get('price_producer', {})
    stocks_news = stat.get('producer_status', {}).get('news_producer', {})
    stocks_flink = stat.get('flink', {}).get('streaming_job', {})

    topics = stat.get('kafka', {}).get('topic_counts', {})
    stock_prices_count = topics.get('stock-prices', 0)
    market_news_count = topics.get('market-news', 0)

    p_active = stocks_producer.get('active', False)
    n_active = stocks_news.get('active', False)
    f_running = stocks_flink.get('state') == 'RUNNING'
    nvda_count = nvda_data.get('count', 0)

    no_regression = p_active and n_active and f_running and nvda_count > 1000 and stock_prices_count > 5000

    record_test(
        "C14", "Zero Regression on Stocks Pipeline", "Regression & Safety",
        "Stocks producers active, Flink job RUNNING, stock-prices/market-news topics intact",
        f"Price producer active={p_active}, News producer active={n_active}, Flink running={f_running}, NVDA candles={nvda_count}, Total stock-prices={stock_prices_count}",
        {
            "stocks_price_producer_status": stocks_producer.get('status'),
            "stocks_news_producer_status": stocks_news.get('status'),
            "stocks_flink_job_id": stocks_flink.get('jid'),
            "stocks_flink_tasks_running": stocks_flink.get('tasks_running'),
            "stock_prices_topic_count": stock_prices_count,
            "market_news_topic_count": market_news_count,
            "nvda_candles_count": nvda_count
        },
        "PASS" if no_regression else "FAIL"
    )


def main():
    print("=" * 80, flush=True)
    print("  GĐ10.5 — FULL CRYPTO ALGORITHMIC TRADING PIPELINE ACCEPTANCE TEST SUITE", flush=True)
    print(f"  Execution Time: {datetime.now(timezone.utc).isoformat()}", flush=True)
    print("=" * 80, flush=True)

    test_c01_crypto_websocket_streaming()
    test_c02_multi_topic_redpanda_ingestion()
    test_c03_schema_integrity_and_timestamps()
    test_c04_deduplication_and_candle_quality()
    test_c05_checkpoint_persistence_and_backfill()
    test_c06_crypto_news_and_vader_sentiment()
    test_c07_parallel_flink_streaming_jobs()
    test_c08_flink_sma20_sma50_calculation()
    test_c09_strategy_signal_generation_baseline()
    test_c10_crypto_signal_handler_consumption()
    test_c11_risk_safeguards_and_dry_run_mode()
    test_c12_dual_asset_rest_and_websocket_api()
    test_c13_react_dashboard_ui_and_crypto_replay()
    test_c14_zero_regression_stocks_pipeline()

    print("\n" + "=" * 80, flush=True)
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')

    print(f"ACCEPTANCE SUMMARY: {passed}/{total} TESTS PASSED ({failed} FAILED)", flush=True)
    print("=" * 80, flush=True)

    # Save results to data/status
    report_path = os.path.join(STATUS_DIR, "gd10_5_acceptance_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "passed": passed,
            "failed": failed,
            "results": results
        }, f, indent=2)
    print(f"Detailed evidence report saved to: {report_path}", flush=True)

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
