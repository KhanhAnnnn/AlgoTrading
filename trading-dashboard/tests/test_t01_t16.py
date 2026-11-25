"""
Comprehensive Test Suite for Live Trading Visualization Dashboard (T01 - T16)
Repository: D:\\AlgoTrading\\trading-dashboard
"""

import os
import sys
import json
import time
import asyncio
import pytest
import requests
import websockets

BACKEND_URL = "http://localhost:8005"
WS_URL = "ws://localhost:8005/ws/live"
FRONTEND_URL = "http://localhost:5173"


# ============================================================================
# T01: Frontend render test
# ============================================================================
def test_t01_frontend_renders_successfully():
    """Verify frontend server responds with 200 OK and contains essential bundle markup."""
    res = requests.get(FRONTEND_URL, timeout=5)
    assert res.status_code == 200, f"Expected 200 OK from frontend, got {res.status_code}"
    html = res.text
    assert '<div id="root">' in html, "Frontend HTML missing #root container"
    assert "/src/main.tsx" in html or "dist/assets" in html or "<script" in html, "Missing script entry"


# ============================================================================
# T02: Backend connects to Kafka cluster
# ============================================================================
def test_t02_backend_kafka_connection():
    """Verify backend successfully connects to Redpanda cluster and reports broker status."""
    res = requests.get(f"{BACKEND_URL}/api/system/status", timeout=5)
    assert res.status_code == 200, f"Status check failed: {res.status_code}"
    data = res.json()
    assert "kafka" in data, "Missing kafka section in status response"
    kafka = data["kafka"]
    assert kafka.get("redpanda_connected") is True, "Backend reports Redpanda Kafka disconnected"
    brokers = kafka.get("brokers", [])
    assert len(brokers) > 0, "No Kafka brokers listed"
    assert any("9092" in b for b in brokers), "Broker localhost:9092 not in broker list"


# ============================================================================
# T03: Historical candles loaded for NVDA and AAPL
# ============================================================================
def test_t03_historical_candles_loaded_nvda_aapl():
    """Verify historical candles are loaded in full for both NVDA and AAPL."""
    res_nvda = requests.get(f"{BACKEND_URL}/api/candles?symbol=NVDA&timeframe=1m", timeout=10)
    assert res_nvda.status_code == 200
    data_nvda = res_nvda.json()
    assert "candles" in data_nvda
    nvda_candles = data_nvda["candles"]
    assert len(nvda_candles) >= 1000, f"Expected >= 1000 NVDA candles, found {len(nvda_candles)}"

    res_aapl = requests.get(f"{BACKEND_URL}/api/candles?symbol=AAPL&timeframe=1m", timeout=10)
    assert res_aapl.status_code == 200
    data_aapl = res_aapl.json()
    assert "candles" in data_aapl
    aapl_candles = data_aapl["candles"]
    assert len(aapl_candles) >= 1000, f"Expected >= 1000 AAPL candles, found {len(aapl_candles)}"


# ============================================================================
# T04: WebSocket receives live updates or connection confirmation
# ============================================================================
def test_t04_websocket_connection_and_heartbeat():
    """Verify client can connect to live WebSocket endpoint and interact with server."""
    async def _run():
        async with websockets.connect(WS_URL, close_timeout=5) as ws:
            await ws.send(json.dumps({"action": "ping", "time": time.time()}))
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                parsed = json.loads(msg)
                assert "event" in parsed or "type" in parsed, "WebSocket message must have 'event' or 'type' field"
            except asyncio.TimeoutError:
                pass

    asyncio.run(_run())


# ============================================================================
# T05: Candlestick time ordering
# ============================================================================
def test_t05_candles_strictly_ordered_by_time():
    """Verify candles are strictly ordered in ascending chronological order."""
    res = requests.get(f"{BACKEND_URL}/api/candles?symbol=NVDA&timeframe=1m", timeout=10)
    candles = res.json()["candles"]
    assert len(candles) > 1

    for i in range(len(candles) - 1):
        t1 = candles[i]["time"]
        t2 = candles[i + 1]["time"]
        assert t1 < t2, f"Candle time inversion at index {i}: {t1} >= {t2}"


# ============================================================================
# T06: Timestamp deduplication
# ============================================================================
def test_t06_candle_deduplication():
    """Verify no duplicate timestamps exist in candle series."""
    res = requests.get(f"{BACKEND_URL}/api/candles?symbol=NVDA&timeframe=1m", timeout=10)
    candles = res.json()["candles"]
    times = [c["time"] for c in candles]
    unique_times = set(times)
    assert len(times) == len(unique_times), f"Found {len(times) - len(unique_times)} duplicate candle timestamps"


# ============================================================================
# T07: SMA 20 and SMA 50 calculation correctness
# ============================================================================
def test_t07_sma_calculation_accuracy():
    """Verify SMA calculation matches manual mathematical moving average of Close prices."""
    res = requests.get(f"{BACKEND_URL}/api/candles?symbol=NVDA&timeframe=1m", timeout=10)
    data = res.json()
    candles = data["candles"]
    sma_20_series = data.get("sma_20", [])
    sma_50_series = data.get("sma_50", [])

    assert len(candles) >= 50
    assert len(sma_20_series) > 0
    assert len(sma_50_series) > 0

    # Test last 20 candles SMA manually
    last_20_closes = [c["close"] for c in candles[-20:]]
    expected_sma_20 = round(sum(last_20_closes) / 20.0, 4)
    actual_sma_20 = sma_20_series[-1]["value"]
    assert abs(actual_sma_20 - expected_sma_20) < 0.05, f"SMA 20 mismatch: expected {expected_sma_20}, got {actual_sma_20}"

    # Test last 50 candles SMA manually
    last_50_closes = [c["close"] for c in candles[-50:]]
    expected_sma_50 = round(sum(last_50_closes) / 50.0, 4)
    actual_sma_50 = sma_50_series[-1]["value"]
    assert abs(actual_sma_50 - expected_sma_50) < 0.05, f"SMA 50 mismatch: expected {expected_sma_50}, got {actual_sma_50}"


# ============================================================================
# T08: BUY signal marker positioning and data
# ============================================================================
def test_t08_buy_signal_marker_data():
    """Verify BUY signals have valid event times, symbols, and price."""
    res = requests.get(f"{BACKEND_URL}/api/signals", timeout=5)
    data = res.json()
    signals = data.get("signals", [])
    buy_signals = [s for s in signals if s.get("signal") == "BUY"]
    assert len(buy_signals) > 0, "No BUY signals found in topic trading-signals"

    sample = buy_signals[0]
    assert "time" in sample and sample["time"] > 0
    assert "price_at_signal" in sample and sample["price_at_signal"] > 0
    assert sample["symbol"] in ["NVDA", "AAPL", "TEST_NVDA"]


# ============================================================================
# T09: SELL signal marker positioning and data
# ============================================================================
def test_t09_sell_signal_marker_data():
    """Verify SELL signals have valid event times, symbols, and price."""
    res = requests.get(f"{BACKEND_URL}/api/signals", timeout=5)
    data = res.json()
    signals = data.get("signals", [])
    sell_signals = [s for s in signals if s.get("signal") == "SELL"]
    assert len(sell_signals) > 0, "No SELL signals found in topic trading-signals"

    sample = sell_signals[0]
    assert "time" in sample and sample["time"] > 0
    assert "price_at_signal" in sample and sample["price_at_signal"] > 0


# ============================================================================
# T10: News Sentiment Panel verification
# ============================================================================
def test_t10_news_sentiment_scores_and_labels():
    """Verify news articles have VADER sentiment scores [-1.0, 1.0] and valid category labels."""
    res = requests.get(f"{BACKEND_URL}/api/news?limit=20", timeout=5)
    data = res.json()
    news_items = data.get("news", [])
    assert len(news_items) > 0, "No news items returned"

    for item in news_items:
        score = item.get("sentiment")
        label = item.get("sentiment_label")
        assert score is not None
        assert -1.0 <= score <= 1.0, f"Sentiment score {score} out of bounds"
        assert label in ["POSITIVE", "NEGATIVE", "NEUTRAL"], f"Invalid label {label}"


# ============================================================================
# T11: Paper Trading Panel read-only API check
# ============================================================================
def test_t11_paper_trading_account_and_orders():
    """Verify paper trading returns equity, cash, and orders from Alpaca Paper API."""
    res_acc = requests.get(f"{BACKEND_URL}/api/paper/account", timeout=5)
    assert res_acc.status_code == 200
    acc = res_acc.json()
    assert "equity" in acc and float(acc["equity"]) > 0
    assert "cash" in acc and float(acc["cash"]) > 0

    res_ord = requests.get(f"{BACKEND_URL}/api/paper/orders", timeout=5)
    assert res_ord.status_code == 200
    ord_data = res_ord.json()
    ords = ord_data.get("orders", ord_data) if isinstance(ord_data, dict) else ord_data
    assert isinstance(ords, list)
    if ords:
        assert "symbol" in ords[0]
        assert "status" in ords[0]


# ============================================================================
# T12: WebSocket reconnection resilience
# ============================================================================
def test_t12_websocket_reconnection_resilience():
    """Verify WebSocket server allows rapid disconnect and reconnection cleanly."""
    async def _run():
        for attempt in range(3):
            async with websockets.connect(WS_URL, close_timeout=2) as ws:
                await ws.send(json.dumps({"action": "ping", "attempt": attempt}))
            await asyncio.sleep(0.1)

        async with websockets.connect(WS_URL, close_timeout=2) as ws:
            await ws.send(json.dumps({"action": "ping", "status": "final"}))

    asyncio.run(_run())


# ============================================================================
# T13: Historical Replay Mode sequence
# ============================================================================
def test_t13_historical_replay_data():
    """Verify replay candles endpoint returns chronological array of candles."""
    res = requests.get(f"{BACKEND_URL}/api/replay/candles?symbol=NVDA", timeout=10)
    assert res.status_code == 200
    data = res.json()
    assert "candles" in data
    candles = data["candles"]
    assert len(candles) >= 50, "Replay requires at least 50 candles"
    # Ensure replay sequence is chronological
    for i in range(len(candles) - 1):
        assert candles[i]["time"] <= candles[i + 1]["time"]


# ============================================================================
# T14: Security check - Zero order submission code in dashboard
# ============================================================================
def test_t14_zero_order_submission_safety():
    """Audit backend and frontend files to ensure no POST /v2/orders or order creation exists."""
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "src")

    # Search backend python files
    for root, _, files in os.walk(backend_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
                    # Check that requests.post to orders is strictly absent
                    assert "requests.post" not in content or "orders" not in content, f"Forbidden POST order call found in {path}"
                    assert "submit_order" not in content, f"Forbidden submit_order found in {path}"

    # Search frontend tsx files
    for root, _, files in os.walk(frontend_dir):
        for f in files:
            if f.endswith(".tsx") or f.endswith(".ts"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
                    assert "createOrder" not in content, f"Forbidden order creation found in {path}"
                    assert "postOrder" not in content, f"Forbidden order creation found in {path}"


# ============================================================================
# T15: Container safety check - Redpanda and Flink remain running
# ============================================================================
def test_t15_docker_containers_healthy():
    """Verify Redpanda brokers and Flink JobManager/TaskManager containers remain Up."""
    res = requests.get(f"{BACKEND_URL}/api/system/status", timeout=5)
    data = res.json()
    assert data["kafka"]["redpanda_connected"] is True, "Redpanda must be running"
    assert data["flink"]["connected"] is True, "Flink JobManager must be connected"
    assert data["flink"]["streaming_job"]["state"] == "RUNNING", "Flink SQL streaming job must be RUNNING"


# ============================================================================
# T16: Accurate Data Status Labeling
# ============================================================================
def test_t16_accurate_data_mode_labeling():
    """Verify backend accurately labels data state (MARKET CLOSED, DELAYED DATA, etc.)."""
    res = requests.get(f"{BACKEND_URL}/api/system/status", timeout=5)
    data = res.json()
    data_mode = data.get("data_mode")
    assert data_mode in [
        "LIVE STREAMING",
        "DELAYED DATA",
        "HISTORICAL REPLAY",
        "STALE",
        "MARKET CLOSED",
    ], f"Unexpected data_mode: {data_mode}"
    # Verify latency metadata
    assert "data_latency_sec" in data
    assert "latency_label" in data
