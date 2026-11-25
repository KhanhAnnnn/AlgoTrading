"""
main.py — FastAPI Backend for Live Trading Visualization Dashboard
Provides REST endpoints and WebSocket streaming for candles, signals, news,
Alpaca Paper portfolio telemetry, and pipeline health monitoring for both Stocks and Crypto 24/7.
"""
import os
import sys
import time
import json
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

from kafka_consumer_service import kafka_service, normalize_crypto_symbol
from timeframe_aggregator import aggregate_candles
from sma_calculator import calculate_smas, get_latest_smas
import alpaca_service
import analytics_service
import observability_service
import reliability_service

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from libs.bot.api import v2_bots_router, v2_ws_router, v2_backtests_router, v2_experiments_router, v2_historical_router

FLINK_REST_URL = os.environ.get('FLINK_REST_URL', 'http://localhost:8081')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch Kafka consumer background thread
    kafka_service.start()
    yield
    # Shutdown: Stop Kafka consumer
    kafka_service.stop()


app = FastAPI(
    title="Real-Time Algorithmic Trading Dashboard API (Stocks & Crypto)",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend Vite dev server & production ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount V2 Paper Trading Bot REST and WebSocket Routers (GĐ35, GĐ36 & GĐ41)
app.include_router(v2_bots_router)
app.include_router(v2_ws_router)
app.include_router(v2_backtests_router)
app.include_router(v2_experiments_router)
app.include_router(v2_historical_router)


@app.get("/api/health")
def health_check():
    return {"status": "UP", "timestamp": int(time.time()), "version": "2.0.0"}


@app.get("/api/candles")
def get_candles(
    symbol: str = Query("NVDA", description="Ticker symbol (e.g. NVDA, AAPL, BTC/USD, ETH/USD)"),
    timeframe: str = Query("1m", description="Timeframe: 1m, 5m, 15m, 1h")
):
    """
    Returns candles for the requested symbol (Stock or Crypto) and timeframe,
    with independently calculated SMA-20 and SMA-50 line series.
    """
    sym = symbol.upper()
    if sym in ('BTCUSD', 'ETHUSD', 'BTC/USD', 'ETH/USD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
    candles_1m = kafka_service.get_candles(sym)

    # If timeframe is not 1m, aggregate cleanly on time boundaries
    candles = aggregate_candles(candles_1m, timeframe=timeframe) if timeframe != '1m' else candles_1m

    sma20_series, sma50_series = calculate_smas(candles)
    smas_info = get_latest_smas(candles)

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
        "sma_20": sma20_series,
        "sma_50": sma50_series,
        "smas_info": smas_info,
    }


@app.get("/api/crypto/candles")
def get_crypto_candles(
    symbol: str = Query("BTC/USD", description="Crypto pair (e.g. BTC/USD, ETH/USD)"),
    timeframe: str = Query("1m", description="Timeframe: 1m, 5m, 15m, 1h")
):
    """Dedicated endpoint for Crypto candles & SMAs."""
    sym = normalize_crypto_symbol(symbol)
    candles_1m = kafka_service.get_crypto_candles(sym)
    candles = aggregate_candles(candles_1m, timeframe=timeframe) if timeframe != '1m' else candles_1m

    sma20_series, sma50_series = calculate_smas(candles)
    smas_info = get_latest_smas(candles)

    return {
        "asset_type": "CRYPTO",
        "symbol": sym,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
        "sma_20": sma20_series,
        "sma_50": sma50_series,
        "smas_info": smas_info,
    }


@app.get("/api/crypto/trades")
def get_crypto_trades(
    symbol: str = Query("BTC/USD", description="Crypto pair"),
    limit: int = Query(50, description="Max trades to return")
):
    """Recent trade ticks for requested crypto pair."""
    sym = normalize_crypto_symbol(symbol)
    trades = kafka_service.get_crypto_trades(sym, limit=limit)
    return {
        "symbol": sym,
        "count": len(trades),
        "trades": trades,
    }


@app.get("/api/signals")
def get_signals(symbol: Optional[str] = None):
    """Returns detected BUY/SELL signals from Kafka, cross-referenced with Paper orders."""
    signals = kafka_service.get_signals(symbol)
    recent_orders = alpaca_service.get_orders(limit=30)

    for sig in signals:
        sig_time = sig.get('time', 0)
        sym = sig.get('symbol', '').upper()
        if sig.get('price_at_signal') is None:
            sym_candles = kafka_service.candles.get(sym, {}) or kafka_service.crypto_candles.get(normalize_crypto_symbol(sym), {})
            if sym_candles:
                closest_time = min(sym_candles.keys(), key=lambda t: abs(t - sig_time))
                sig['price_at_signal'] = sym_candles[closest_time].get('close')

        matched_order = None
        for ord_item in recent_orders:
            ord_sym = ord_item.get('symbol', '').upper()
            if ord_sym == sym or ord_sym == sym.replace('/', ''):
                matched_order = ord_item
                break
        sig['paper_order'] = matched_order

    return {
        "count": len(signals),
        "signals": signals,
    }


@app.get("/api/crypto/signals")
def get_crypto_signals(symbol: Optional[str] = None):
    """Returns crypto BUY/SELL signals from 'crypto-signals' topic."""
    signals = kafka_service.get_crypto_signals(symbol)
    recent_orders = alpaca_service.get_orders(limit=30)

    for sig in signals:
        sym = sig.get('symbol', '')
        matched_order = None
        for ord_item in recent_orders:
            ord_sym = ord_item.get('symbol', '').upper()
            if ord_sym == sym or ord_sym == sym.replace('/', ''):
                matched_order = ord_item
                break
        sig['paper_order'] = matched_order

    return {
        "asset_type": "CRYPTO",
        "count": len(signals),
        "signals": signals,
    }


@app.get("/api/news")
def get_news(
    symbol: Optional[str] = None,
    sentiment: Optional[str] = None
):
    """Returns financial and crypto news with VADER sentiment scores and optional filters."""
    news_items = kafka_service.get_news(symbol=symbol, sentiment_filter=sentiment)
    return {
        "count": len(news_items),
        "news": news_items,
    }


@app.get("/api/crypto/news")
def get_crypto_news(
    symbol: Optional[str] = None,
    sentiment: Optional[str] = None
):
    """Returns crypto-specific news with sentiment."""
    news_items = kafka_service.get_crypto_news(symbol=symbol, sentiment_filter=sentiment)
    return {
        "asset_type": "CRYPTO",
        "count": len(news_items),
        "news": news_items,
    }


@app.get("/api/paper/account")
def get_paper_account():
    """Read-only Alpaca Paper Trading account overview."""
    return alpaca_service.get_account()


@app.get("/api/paper/positions")
def get_paper_positions():
    """Read-only Alpaca Paper Trading open positions (Stocks and Crypto)."""
    return alpaca_service.get_positions()


@app.get("/api/paper/orders")
def get_paper_orders(limit: int = 20):
    """Read-only Alpaca Paper Trading recent orders."""
    return alpaca_service.get_orders(limit=limit)


@app.get("/api/paper/summary")
def get_paper_summary():
    """Returns consolidated Alpaca Paper portfolio summary, unrealized P/L, and order breakdown."""
    return alpaca_service.get_portfolio_summary()


@app.get("/api/analytics/strategies")
def get_strategies_analytics(
    asset: str = Query("NVDA", description="Asset ticker: NVDA, AAPL, BTC/USD, ETH/USD"),
    split: str = Query("FULL_PERIOD", description="Data partition: FULL_PERIOD, TRAIN_SAMPLE, VAL_SAMPLE, TEST_OUT_OF_SAMPLE")
):
    """Returns comparative metrics across all 5 quantitative strategies."""
    sym = asset.upper()
    if sym in ('BTCUSD', 'ETHUSD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
    return {
        "asset": sym,
        "split": split,
        "strategies": analytics_service.get_strategies_summary(asset=sym, split=split)
    }


@app.get("/api/analytics/equity-curve")
def get_equity_curve_endpoint(
    asset: str = Query("NVDA", description="Asset ticker"),
    strategy_id: int = Query(1, description="Strategy ID (1 to 5)")
):
    """Returns equity curve points, rolling drawdown, and benchmark for visualization."""
    sym = asset.upper()
    if sym in ('BTCUSD', 'ETHUSD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
    return analytics_service.get_equity_curve(asset=sym, strategy_id=strategy_id)


@app.get("/api/analytics/trades")
def get_trades_endpoint(
    asset: Optional[str] = Query(None, description="Optional asset filter"),
    strategy_id: Optional[int] = Query(None, description="Optional strategy ID (1 to 5)")
):
    """Returns historical backtest trades simulated with execution friction."""
    sym = asset.upper() if asset else None
    if sym in ('BTCUSD', 'ETHUSD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
    trades = analytics_service.get_historical_trades(asset=sym, strategy_id=strategy_id)
    return {
        "count": len(trades),
        "trades": trades
    }


@app.get("/api/analytics/splits")
def get_splits_endpoint(
    asset: str = Query("NVDA", description="Asset ticker"),
    strategy_id: int = Query(1, description="Strategy ID (1 to 5)")
):
    """Returns out-of-sample data split breakdown (Train, Val, Test)."""
    sym = asset.upper()
    if sym in ('BTCUSD', 'ETHUSD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
    return {
        "asset": sym,
        "strategy_id": strategy_id,
        "splits": analytics_service.get_out_of_sample_splits(asset=sym, strategy_id=strategy_id)
    }


@app.get("/api/observability/stream")
def get_streaming_observability_endpoint():
    """Returns detailed streaming infrastructure telemetry: Kafka offsets, consumer lag, Flink checkpoints."""
    return observability_service.get_streaming_telemetry()


@app.get("/api/reliability/events")
def get_reliability_events_endpoint():
    """Returns recovery events, Slack outbox messages, dead-letter queue, and signal dedup state."""
    return reliability_service.get_reliability_telemetry()



@app.get("/api/system/status")
def get_system_status():
    """
    Returns end-to-end pipeline health:
    Redpanda cluster, Stocks Flink job, Crypto Flink job, producer health, latency, and data mode.
    """
    kafka_status = kafka_service.get_status()

    # Query Flink JobManager REST API
    flink_status = {
        "connected": False,
        "jobs": [],
        "streaming_job": None,
        "crypto_streaming_job": None,
    }
    try:
        r = requests.get(f"{FLINK_REST_URL}/jobs/overview", timeout=2)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            flink_status["connected"] = True
            flink_status["jobs"] = jobs
            for j in jobs:
                j_name = j.get("name", "")
                job_info = {
                    "jid": j.get("jid"),
                    "name": j_name,
                    "state": j.get("state"),
                    "tasks_running": j.get("tasks", {}).get("running", 0),
                    "tasks_total": j.get("tasks", {}).get("total", 0),
                }
                if "crypto_signals" in j_name:
                    flink_status["crypto_streaming_job"] = job_info
                elif "trading_signals" in j_name:
                    flink_status["streaming_job"] = job_info
    except Exception as e:
        flink_status["error"] = str(e)

    # Read Producer Health Files
    base_project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    status_dir = os.path.join(base_project_dir, 'data', 'status')
    price_health_file = os.path.join(status_dir, 'price_producer_health.json')
    news_health_file = os.path.join(status_dir, 'news_producer_health.json')
    crypto_health_file = os.path.join(status_dir, 'crypto_producer_health.json')
    crypto_handler_health_file = os.path.join(status_dir, 'crypto_handler_health.json')

    producer_status = {
        "price_producer": {"status": "UNKNOWN", "active": False},
        "news_producer": {"status": "UNKNOWN", "active": False},
        "crypto_producer": {"status": "UNKNOWN", "active": False},
        "crypto_handler": {"status": "UNKNOWN", "active": False},
    }

    def _read_health(path: str, max_age_sec: int) -> Dict[str, Any]:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    hb = d.get('last_heartbeat', '')
                    age = time.time() - datetime.fromisoformat(hb).timestamp() if hb else 9999
                    d['active'] = age < max_age_sec
                    return d
            except Exception:
                pass
        return {"status": "NOT_RUNNING", "active": False}

    producer_status["price_producer"] = _read_health(price_health_file, 180)
    producer_status["news_producer"] = _read_health(news_health_file, 240)
    producer_status["crypto_producer"] = _read_health(crypto_health_file, 180)
    producer_status["crypto_handler"] = _read_health(crypto_handler_health_file, 180)

    # Check Alpaca Market Clock for Stocks
    market_clock = alpaca_service.get_clock()
    is_market_open = market_clock.get("is_open", False)

    # Determine Stocks Data Mode and Latency
    last_price_ts = kafka_status.get("last_event_timestamps", {}).get("stock-prices")
    last_ingest_ts = kafka_status.get("last_ingestion_timestamps", {}).get("stock-prices")
    now_ts = int(time.time())

    data_latency_sec = None
    data_mode = "MARKET CLOSED"
    latency_label = "Unknown"

    if not kafka_status.get("redpanda_connected"):
        data_mode = "RECONNECTING"
        latency_label = "Reconnecting to Redpanda brokers..."
    elif not is_market_open:
        data_mode = "MARKET CLOSED"
        if last_price_ts:
            bar_time = datetime.fromtimestamp(last_price_ts, tz=timezone.utc).strftime('%b %d, %H:%M UTC')
            latency_label = f"Market Closed (Last bar: {bar_time})"
            data_latency_sec = max(0, now_ts - last_price_ts)
        else:
            latency_label = "Market Closed (No data)"
    else:
        # Market is OPEN
        if last_price_ts:
            data_latency_sec = max(0, now_ts - last_price_ts)
            if data_latency_sec < 180:
                data_mode = "LIVE STREAMING"
                latency_label = f"Live ({data_latency_sec}s latency)"
            elif data_latency_sec <= 1500:
                mins = data_latency_sec // 60
                secs = data_latency_sec % 60
                data_mode = "DELAYED DATA"
                latency_label = f"Delayed {mins}m {secs}s (Alpaca IEX feed)"
            else:
                data_mode = "STALE"
                mins = data_latency_sec // 60
                latency_label = f"Stale ({mins}m without updates)"
        else:
            data_mode = "WAITING FOR DATA"
            latency_label = "Waiting for initial bars..."

    # Crypto 24/7 Status
    last_crypto_bar_ts = kafka_status.get("last_event_timestamps", {}).get("crypto-bars-1m")
    crypto_latency_sec = max(0, now_ts - last_crypto_bar_ts) if last_crypto_bar_ts else None
    if not kafka_status.get("redpanda_connected"):
        crypto_mode = "RECONNECTING"
        crypto_latency_label = "Reconnecting..."
    elif last_crypto_bar_ts:
        if crypto_latency_sec < 180:
            crypto_mode = "LIVE STREAMING"
            crypto_latency_label = f"Live 24/7 ({crypto_latency_sec}s latency)"
        elif crypto_latency_sec <= 900:
            crypto_mode = "DELAYED DATA"
            crypto_latency_label = f"Delayed {crypto_latency_sec // 60}m"
        else:
            crypto_mode = "STALE"
            crypto_latency_label = f"Stale ({crypto_latency_sec // 60}m)"
    else:
        crypto_mode = "WAITING FOR DATA"
        crypto_latency_label = "Waiting for crypto stream..."

    last_candle_iso = datetime.fromtimestamp(last_price_ts, tz=timezone.utc).isoformat() if last_price_ts else None
    last_ingest_iso = datetime.fromtimestamp(last_ingest_ts, tz=timezone.utc).isoformat() if last_ingest_ts else None
    last_crypto_candle_iso = datetime.fromtimestamp(last_crypto_bar_ts, tz=timezone.utc).isoformat() if last_crypto_bar_ts else None

    telemetry = observability_service.get_streaming_telemetry()
    pipeline_verdict = telemetry.get("pipeline_verdict", "HEALTHY")
    pipeline_verdict_label = telemetry.get("pipeline_verdict_label", "All Systems Nominal")
    health_pillars = telemetry.get("health_pillars", {})

    return {
        "backend_time": now_ts,
        "pipeline_verdict": pipeline_verdict,
        "pipeline_verdict_label": pipeline_verdict_label,
        "health_pillars": health_pillars,
        "data_mode": data_mode,
        "data_latency_sec": data_latency_sec,
        "latency_label": latency_label,
        "market_open": is_market_open,
        "market_clock": market_clock,
        "crypto_mode": crypto_mode,
        "crypto_latency_sec": crypto_latency_sec,
        "crypto_latency_label": crypto_latency_label,
        "last_candle_timestamp": last_candle_iso,
        "last_candle_ts_sec": last_price_ts,
        "last_crypto_candle_timestamp": last_crypto_candle_iso,
        "last_crypto_candle_ts_sec": last_crypto_bar_ts,
        "last_ingestion_timestamp": last_ingest_iso,
        "producer_status": producer_status,
        "kafka": kafka_status,
        "flink": flink_status,
    }


@app.get("/api/replay/candles")
def get_replay_candles(symbol: str = Query("NVDA")):
    """Returns chronological candles for client-side Historical Replay mode (Stocks & Crypto)."""
    sym = symbol.upper()
    if sym in ('BTCUSD', 'ETHUSD', 'BTC/USD', 'ETH/USD', 'BTC-USD', 'ETH-USD'):
        sym = normalize_crypto_symbol(sym)
        candles_1m = kafka_service.get_crypto_candles(sym)
    else:
        candles_1m = kafka_service.get_candles(sym)

    return {
        "symbol": sym,
        "total": len(candles_1m),
        "candles": candles_1m,
    }


@app.get("/api/crypto/replay/candles")
def get_crypto_replay_candles(symbol: str = Query("BTC/USD")):
    """Dedicated endpoint for Crypto Historical Replay."""
    sym = normalize_crypto_symbol(symbol)
    candles_1m = kafka_service.get_crypto_candles(sym)
    return {
        "asset_type": "CRYPTO",
        "symbol": sym,
        "total": len(candles_1m),
        "candles": candles_1m,
    }


@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    """
    Real-time streaming WebSocket endpoint.
    Broadcasts candle updates, trades, signals, news, and periodic heartbeats.
    """
    await websocket.accept()
    q = asyncio.Queue()
    kafka_service.register_ws(q)

    # Send initial greeting snapshot
    await websocket.send_json({
        "type": "welcome",
        "data": {
            "server_time": int(time.time()),
            "status": "connected",
            "message": "Connected to Real-Time AlgoTrading Stream (Stocks & Crypto)",
        }
    })

    async def sender_task():
        try:
            while True:
                msg = await q.get()
                await websocket.send_json(msg)
                q.task_done()
        except asyncio.CancelledError:
            pass

    async def heartbeat_task():
        try:
            while True:
                await asyncio.sleep(10)
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {"server_time": int(time.time())}
                })
        except asyncio.CancelledError:
            pass

    t1 = asyncio.create_task(sender_task())
    t2 = asyncio.create_task(heartbeat_task())

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        t1.cancel()
        t2.cancel()
        kafka_service.unregister_ws(q)


@app.get("/api/shadow/observations")
def get_shadow_observations(limit: int = 50, symbol: Optional[str] = None):
    """Retrieve recent Shadow Mode signal observations (strictly read-only)."""
    try:
        from shadow_mode_observer import shadow_observer
        return shadow_observer.get_recent_observations(limit=limit, symbol=symbol)
    except Exception as e:
        return {"error": str(e), "observations": []}


@app.get("/api/shadow/metrics")
def get_shadow_metrics():
    """Retrieve forward validation metrics and SLA compliance counters."""
    try:
        from shadow_mode_observer import shadow_observer
        return shadow_observer.get_metrics()
    except Exception as e:
        return {"error": str(e)}


# ==============================================================================
# GĐ19 — TRADING WORKBENCH & ORDER MANAGEMENT (SIMULATION BROKER)
# ==============================================================================
from pydantic import BaseModel, Field

class OrderSubmissionRequest(BaseModel):
    symbol: str
    side: str
    type: str = "market"
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: Optional[str] = "day"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_price: Optional[float] = None
    trail_percent: Optional[float] = None
    client_order_id: Optional[str] = None
    order_class: Optional[str] = "simple"
    target_broker: Optional[str] = "MOCK"

class OrderReplaceRequest(BaseModel):
    qty: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: Optional[str] = None
    client_order_id: Optional[str] = None

@app.get("/api/paper/orders/{order_id}")
def get_paper_order_details(order_id: str):
    """Fetch individual Alpaca Paper order details directly from broker."""
    from alpaca_paper_gate import paper_gate
    return paper_gate.get_order_by_id(order_id)

@app.get("/api/paper/activities")
def get_paper_activities(activity_type: Optional[str] = None, limit: int = 50):
    """Retrieve historical account activities from Alpaca Paper (FILL, CFEE, FEE, JNLC)."""
    from alpaca_paper_gate import paper_gate
    return paper_gate.get_account_activities(activity_type=activity_type, limit=limit)

@app.get("/api/paper/sync/reconcile")
def get_paper_sync_reconcile():
    """Reconciles Alpaca Paper read-only telemetry with TradingStream event cache."""
    from alpaca_paper_gate import paper_gate
    from alpaca_order_stream_processor import stream_processor
    rest_orders = paper_gate.get_orders(status="all", limit=100)
    return stream_processor.reconcile_with_rest(rest_orders)

@app.get("/api/paper/stream/status")
def get_paper_stream_status():
    """Returns TradingStream event cache status, metrics, and connection state."""
    from alpaca_order_stream_processor import stream_processor
    return {
        "connection_status": stream_processor.connection_status,
        "reconnect_count": stream_processor.reconnect_count,
        "metrics": stream_processor.metrics,
        "cached_orders_count": len(stream_processor.order_cache),
        "events_logged_count": len(stream_processor.events_log)
    }

@app.get("/api/workbench/account")
def get_workbench_account(source: str = Query("mock", description="Source: 'mock' or 'alpaca_paper'")):
    """Retrieve trading account balance, equity, and buying power (Mock or Alpaca Paper)."""
    if source.lower() == "alpaca_paper":
        from alpaca_paper_gate import paper_gate
        return paper_gate.get_account_overview()
    from mock_trading_broker import mock_broker
    acc = mock_broker.get_account()
    acc["data_source"] = "MOCK"
    return acc

@app.get("/api/workbench/positions")
def get_workbench_positions(source: str = Query("mock", description="Source: 'mock' or 'alpaca_paper'")):
    """Retrieve open positions (Mock or Alpaca Paper)."""
    if source.lower() == "alpaca_paper":
        from alpaca_paper_gate import paper_gate
        return paper_gate.get_positions()
    from mock_trading_broker import mock_broker
    return mock_broker.get_positions()

@app.get("/api/workbench/orders")
def get_workbench_orders(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    limit: int = 50,
    source: str = Query("mock", description="Source: 'mock' or 'alpaca_paper'")
):
    """Retrieve filtered orders (Mock or Alpaca Paper)."""
    if source.lower() == "alpaca_paper":
        from alpaca_paper_gate import paper_gate
        orders = paper_gate.get_orders(status=status or "all", limit=limit)
        if symbol:
            orders = [o for o in orders if o.get("symbol") == symbol.upper()]
        if side:
            orders = [o for o in orders if o.get("side") == side.lower()]
        return orders
    from mock_trading_broker import mock_broker
    return mock_broker.get_orders(status=status, symbol=symbol, side=side, limit=limit)

@app.get("/api/workbench/orders/{order_id}")
def get_workbench_order_details(order_id: str):
    """Retrieve individual simulated order details along with lifecycle activities."""
    from mock_trading_broker import mock_broker
    order = mock_broker.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Simulated order '{order_id}' not found")
    activities = mock_broker.get_activities(order_id=order_id)
    return {"order": order, "activities": activities}

@app.post("/api/workbench/orders")
def create_workbench_order(order_req: OrderSubmissionRequest):
    """Submit a validated simulated order to the Mock Broker engine."""
    if order_req.target_broker and order_req.target_broker.upper() == "ALPACA_PAPER":
        raise HTTPException(
            status_code=403,
            detail="CRITICAL SAFETY GUARD: Direct order submission to Alpaca Paper is locked by Paper Execution Gate."
        )
    from mock_trading_broker import mock_broker
    try:
        order = mock_broker.submit_order(order_req.dict(exclude_none=True))
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/workbench/orders/{order_id}")
def replace_workbench_order(order_id: str, replace_req: OrderReplaceRequest):
    """Replace an active simulated order."""
    from mock_trading_broker import mock_broker
    try:
        updated = mock_broker.replace_order(order_id, replace_req.dict(exclude_none=True))
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/workbench/orders/{order_id}")
def cancel_workbench_order(order_id: str):
    """Cancel an open simulated order."""
    from mock_trading_broker import mock_broker
    try:
        canceled = mock_broker.cancel_order(order_id)
        return canceled
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/workbench/orders")
def cancel_all_workbench_orders():
    """Cancel all active open simulated orders."""
    from mock_trading_broker import mock_broker
    canceled = mock_broker.cancel_all_orders()
    return {"canceled_count": len(canceled), "canceled_orders": canceled}

@app.get("/api/workbench/activities")
def get_workbench_activities(order_id: Optional[str] = None, limit: int = 100):
    """Retrieve simulated order lifecycle audit events."""
    from mock_trading_broker import mock_broker
    return mock_broker.get_activities(order_id=order_id, limit=limit)

@app.post("/api/workbench/reset")
def reset_workbench_account(initial_cash: Optional[float] = 100000.0):
    """Reset simulated trading account and clear all mock positions."""
    from mock_trading_broker import mock_broker
    return mock_broker.reset_account(initial_cash=initial_cash)

# ==============================================================================
# SERVER-SIDE EXECUTION SAFETY GUARDS (STRICT DRY_RUN ENFORCEMENT)
# ==============================================================================
@app.post("/api/orders")
@app.post("/api/trade")
@app.post("/api/v2/orders")
def reject_live_order_attempts():
    """
    Explicit server-side safety guard: Intercepts and blocks any attempt to submit live orders.
    """
    raise HTTPException(
        status_code=403,
        detail="CRITICAL SAFETY GUARD: Live and unsimulated order placement is strictly prohibited. TRADING_MODE is locked to DRY_RUN."
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=False)
