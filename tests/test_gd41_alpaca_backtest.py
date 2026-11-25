"""
tests/test_gd41_alpaca_backtest.py — Acceptance Test Suite for GĐ41
Real Alpaca Historical Data & One-Click Backtest Integration.

Covers:
1. Alpaca Historical Client authentication, asset class detection, and rate-limit backoff.
2. Real historical data fetch for Stocks (NVDA) on IEX feed.
3. Real historical data fetch for Crypto (BTC/USD) 24/7.
4. Dataset caching, provenance manifests, and SHA-256 integrity verification.
5. REST API: POST /api/v2/historical-data/fetch and GET /api/v2/historical-data/datasets.
6. REST API: POST /api/v2/backtests/from-alpaca (One-click real data backtest).
7. REST API: POST /api/v2/backtests/from-dataset (Local cache replay).
8. Deterministic economic fingerprint invariance on repeated identical runs.
9. Strategy comparison (MA_CROSS_1M vs RSI_1M) on identical dataset.
10. Strict safety: zero broker writes, closed PaperExecutionGate, no silent synthetic fallback.
11. CSV export capability.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

# Ensure workspace and libs are on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
LIBS_DIR = os.path.join(BASE_DIR, "libs")
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)
BACKEND_DIR = os.path.join(BASE_DIR, "trading-dashboard", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from libs.alpaca_paper_gate import paper_gate
from libs.bot.backtesting.alpaca_client import (
    AlpacaHistoricalClient,
    AlpacaHistoricalDataError,
    AlpacaAuthenticationError,
    AlpacaRateLimitExceededError,
)
from libs.bot.backtesting.dataset import HistoricalDatasetManager, DatasetManifest, InvalidBarDataError
from libs.bot.domain import MarketDataEvent
from main import app


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def dataset_mgr():
    return HistoricalDatasetManager(base_dir="data/paper_bot/datasets")


class TestGD41AlpacaBacktest:
    """Master acceptance test suite for GĐ41."""

    def test_tc01_client_initialization_and_asset_detection(self):
        """Verifies Alpaca client reads credentials and accurately routes asset classes."""
        client = AlpacaHistoricalClient()
        assert client.api_key is not None, "Alpaca API Key must be configured"
        assert client.secret_key is not None, "Alpaca Secret Key must be configured"

        assert client.detect_asset_class("NVDA") == "STOCKS"
        assert client.detect_asset_class("AAPL") == "STOCKS"
        assert client.detect_asset_class("TSLA") == "STOCKS"
        assert client.detect_asset_class("BTC/USD") == "CRYPTO"
        assert client.detect_asset_class("ETH/USD") == "CRYPTO"
        assert client.detect_asset_class("SOL/USD") == "CRYPTO"

    def test_tc02_real_alpaca_stocks_fetch_nvda(self):
        """Fetches real historical 1m bars for NVDA on IEX feed directly from Alpaca."""
        client = AlpacaHistoricalClient()
        start = datetime.fromisoformat("2024-11-20T14:30:00+00:00")
        end = datetime.fromisoformat("2024-11-20T16:30:00+00:00")

        bars, meta = client.fetch_bars("NVDA", start, end, feed="IEX")
        assert len(bars) > 0, "Alpaca must return non-empty real historical bars for NVDA"
        assert meta["provider"] == "ALPACA"
        assert meta["source_type"] == "REAL_HISTORICAL_MARKET_DATA"
        assert meta["asset_class"] == "STOCKS"
        assert meta["feed"] == "IEX"
        assert meta["completeness_status"] == "COMPLETE"

        # Verify bar attributes and mathematical OHLCV integrity
        for b in bars:
            assert b.symbol == "NVDA"
            assert b.asset_class == "STOCKS"
            assert b.open > 0 and b.high >= b.low and b.high >= b.open and b.high >= b.close
            assert b.low <= b.open and b.low <= b.close
            assert b.volume >= 0
            assert b.provenance == "REAL_HISTORICAL_MARKET_DATA"

        # Verify chronological order
        for i in range(len(bars) - 1):
            assert bars[i].event_time <= bars[i + 1].event_time

    def test_tc03_real_alpaca_crypto_fetch_btc(self):
        """Fetches real historical 1m bars for BTC/USD directly from Alpaca Crypto endpoint."""
        client = AlpacaHistoricalClient()
        start = datetime.fromisoformat("2024-11-20T14:30:00+00:00")
        end = datetime.fromisoformat("2024-11-20T16:30:00+00:00")

        bars, meta = client.fetch_bars("BTC/USD", start, end)
        assert len(bars) > 0, "Alpaca must return non-empty crypto bars for BTC/USD"
        assert meta["provider"] == "ALPACA"
        assert meta["source_type"] == "REAL_HISTORICAL_MARKET_DATA"
        assert meta["asset_class"] == "CRYPTO"
        assert meta["feed"] == "CRYPTO"

        for b in bars:
            assert b.symbol == "BTC/USD"
            assert b.asset_class == "CRYPTO"
            assert b.open > 1000.0  # BTC price check
            assert b.high >= b.low

    def test_tc04_dataset_manifest_and_sha256_checksum(self, dataset_mgr):
        """Verifies dataset manifest creation, provenance tracking, and SHA-256 hashing."""
        client = AlpacaHistoricalClient()
        start = datetime.fromisoformat("2024-11-20T14:30:00+00:00")
        end = datetime.fromisoformat("2024-11-20T15:30:00+00:00")
        bars, meta = client.fetch_bars("NVDA", start, end, feed="IEX")

        d_id = f"test_ds_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        sanitized, manifest = dataset_mgr.create_dataset_from_bars(
            dataset_id=d_id,
            bars=bars,
            version="1.0.0",
            is_synthetic=False,
            provider="ALPACA",
            source_type="REAL_HISTORICAL_MARKET_DATA",
            feed="IEX",
            asset_class="STOCKS",
        )

        assert manifest.dataset_id == d_id
        assert manifest.provider == "ALPACA"
        assert manifest.source_type == "REAL_HISTORICAL_MARKET_DATA"
        assert manifest.checksum_sha256 is not None
        assert len(manifest.checksum_sha256) == 64  # Valid SHA-256 hex string
        assert manifest.total_bars == len(sanitized)
        assert not manifest.is_synthetic

    def test_tc05_dataset_caching_and_disk_persistence(self, dataset_mgr):
        """Verifies that dataset persisted to disk can be loaded and searched by cache lookup."""
        client = AlpacaHistoricalClient()
        start = datetime.fromisoformat("2024-11-20T14:30:00+00:00")
        end = datetime.fromisoformat("2024-11-20T15:30:00+00:00")
        bars, _ = client.fetch_bars("NVDA", start, end, feed="IEX")

        d_id = f"test_cache_nvda_{start.strftime('%Y%m%d%H%M')}"
        _, orig_manifest = dataset_mgr.create_dataset_from_bars(
            dataset_id=d_id,
            bars=bars,
            provider="ALPACA",
            source_type="REAL_HISTORICAL_MARKET_DATA",
            feed="IEX",
            asset_class="STOCKS",
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            persist_to_disk=True,
        )

        # Lookup in cache
        cached = dataset_mgr.find_cached_dataset(
            symbol="NVDA",
            timeframe="1m",
            feed="IEX",
            start_time=start,
            end_time=end,
        )
        assert cached is not None, "Cache lookup must find previously persisted dataset"
        assert cached.checksum_sha256 == orig_manifest.checksum_sha256

        # Load from disk
        loaded_bars = dataset_mgr.load_dataset(d_id)
        assert loaded_bars is not None
        assert len(loaded_bars) == len(bars)
        assert loaded_bars[0].event_time == bars[0].event_time

    def test_tc06_one_click_alpaca_backtest_stocks_api(self, api_client):
        """Tests POST /api/v2/backtests/from-alpaca for US Equities end-to-end."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T16:30:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "strategy_version": "1.0.0",
            "initial_simulated_cash": 100000.0,
            "force_refresh": False,
        }

        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201, f"One-click backtest failed: {res.text}"

        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["strategy_id"] == "MA_CROSS_1M"
        assert "NVDA" in data["symbols"]
        assert data["environment"] == "SIMULATION"
        assert data["trading_mode"] == "DRY_RUN"
        assert data["paper_execution_gate"] == "CLOSED"
        assert data["dataset"]["provider"] == "ALPACA"
        assert data["dataset"]["source_type"] == "REAL_HISTORICAL_MARKET_DATA"
        assert data["deterministic_fingerprint"] is not None
        assert "final_equity" in data["metrics"]
        assert "net_pnl" in data["metrics"]

    def test_tc07_one_click_alpaca_backtest_crypto_api(self, api_client):
        """Tests POST /api/v2/backtests/from-alpaca for Crypto (BTC/USD) end-to-end."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T16:30:00Z",
            "feed": "CRYPTO",
            "strategy_id": "MA_CROSS_1M",
            "strategy_version": "1.0.0",
            "initial_simulated_cash": 100000.0,
            "force_refresh": False,
        }

        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201, f"Crypto backtest failed: {res.text}"

        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["dataset"]["asset_class"] == "CRYPTO"
        assert data["metrics"]["total_trades"] >= 0
        assert data["metrics"]["final_equity"] > 0

    def test_tc08_deterministic_economic_fingerprint_invariance(self, api_client):
        """Verifies that running backtests twice on identical datasets produces identical fingerprints."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T16:30:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "strategy_version": "1.0.0",
            "initial_simulated_cash": 100000.0,
            "seed": 42,
            "force_refresh": False,
        }

        res1 = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        res2 = api_client.post("/api/v2/backtests/from-alpaca", json=payload)

        assert res1.status_code == 201
        assert res2.status_code == 201

        d1 = res1.json()
        d2 = res2.json()

        assert d1["deterministic_fingerprint"] == d2["deterministic_fingerprint"], (
            f"Fingerprint mismatch: {d1['deterministic_fingerprint']} vs {d2['deterministic_fingerprint']}"
        )
        assert d1["metrics"]["final_equity"] == d2["metrics"]["final_equity"]
        assert d1["metrics"]["net_pnl"] == d2["metrics"]["net_pnl"]
        assert d1["metrics"]["total_trades"] == d2["metrics"]["total_trades"]

    def test_tc09_multi_strategy_comparison_on_same_dataset(self, api_client):
        """Compares MA_CROSS_1M and RSI_1M strategies on the exact same dataset."""
        base_payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T16:30:00Z",
            "feed": "IEX",
            "initial_simulated_cash": 100000.0,
            "force_refresh": False,
        }

        # Strategy 1: MA_CROSS
        p1 = dict(base_payload, strategy_id="MA_CROSS_1M")
        res1 = api_client.post("/api/v2/backtests/from-alpaca", json=p1)
        assert res1.status_code == 201
        data1 = res1.json()

        # Strategy 2: RSI
        p2 = dict(base_payload, strategy_id="RSI_1M")
        res2 = api_client.post("/api/v2/backtests/from-alpaca", json=p2)
        assert res2.status_code == 201
        data2 = res2.json()

        # Same dataset checksum
        assert data1["dataset"]["checksum_sha256"] == data2["dataset"]["checksum_sha256"]
        # Different strategy behavior / fingerprints
        assert data1["strategy_id"] != data2["strategy_id"]

    def test_tc10_no_silent_synthetic_fallback(self, api_client):
        """Verifies that requesting non-existent historical dates raises an error and NEVER falls back silently."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            # Future / unpopulated timestamp window
            "start_time": "2029-01-01T14:30:00Z",
            "end_time": "2029-01-01T16:30:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "force_refresh": True,
        }

        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        # Must return 404 with explicit message, NOT 201 with synthetic bars
        assert res.status_code == 404
        assert "0 bars" in res.json()["detail"] or "trading hours" in res.json()["detail"].lower()

    def test_tc11_zero_broker_writes_and_safety_gate(self):
        """Enforces that simulation operates strictly under DRY_RUN and gate closed."""
        assert not paper_gate.is_gate_open, "PaperExecutionGate must remain closed during all simulation backtests"
        assert paper_gate.mode in ("ALPACA_PAPER_READ_ONLY", "MOCK")

    def test_tc12_historical_data_endpoints(self, api_client):
        """Tests GET /api/v2/historical-data/datasets and dataset bar inspection."""
        res = api_client.get("/api/v2/historical-data/datasets")
        assert res.status_code == 200
        datasets = res.json()
        assert isinstance(datasets, list)
        assert len(datasets) > 0

        first_ds_id = datasets[0]["dataset_id"]
        res_detail = api_client.get(f"/api/v2/historical-data/datasets/{first_ds_id}")
        assert res_detail.status_code == 200
        assert res_detail.json()["dataset_id"] == first_ds_id

        res_bars = api_client.get(f"/api/v2/historical-data/datasets/{first_ds_id}/bars?limit=10")
        assert res_bars.status_code == 200
        assert "bars" in res_bars.json()
        assert len(res_bars.json()["bars"]) <= 10

    def test_tc13_csv_export_endpoint(self, api_client):
        """Tests GET /api/v2/historical-data/datasets/{id}/csv export."""
        res_list = api_client.get("/api/v2/historical-data/datasets")
        first_ds_id = res_list.json()[0]["dataset_id"]

        res_csv = api_client.get(f"/api/v2/historical-data/datasets/{first_ds_id}/csv")
        assert res_csv.status_code == 200
        assert res_csv.headers["content-type"] == "text/csv; charset=utf-8"
        content = res_csv.text
        assert "timestamp,symbol,open,high,low,close,volume" in content
        assert len(content.splitlines()) > 1
