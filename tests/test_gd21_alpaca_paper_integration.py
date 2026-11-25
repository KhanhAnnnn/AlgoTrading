"""
tests/test_gd21_alpaca_paper_integration.py — GĐ21 Alpaca Paper Trading Integration Test Suite
Verifies:
1. GĐ21.1 Read-Only Account Synchronization (Account Overview, Positions, Orders, Order Details, Filtering, Balance Provenance)
2. GĐ21.2 Order Updates via TradingStream (Deduplication, Out-of-order precedence, Unknown events, Reconnect, REST Reconciliation)
3. GĐ21.3 Paper Execution Gate & Safety Guardrails (Fail-closed default, Fake transport testing, Live URL block, Zero network write calls)
4. State storage segregation between Mock Broker and Alpaca Paper
5. Non-regression of existing dashboard APIs and GĐ18 soak runtime preservation
"""

import os
import sys
import json
import time
import uuid
import unittest
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIBS_DIR = os.path.join(BASE_DIR, "libs")
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_paper_gate import (
    AlpacaPaperGate,
    PaperExecutionGateClosedError,
    LiveTradingProhibitedError,
    paper_gate
)
from alpaca_order_stream_processor import (
    AlpacaOrderStreamProcessor,
    stream_processor
)

API_BASE = "http://127.0.0.1:8005"
FLINK_BASE = "http://127.0.0.1:8081"


class TestGD21AlpacaPaperIntegration(unittest.TestCase):

    # =========================================================================
    # GROUP 1: READ-ONLY ACCOUNT SYNCHRONIZATION (TC-G21-01 to TC-G21-07)
    # =========================================================================

    def test_01_paper_account_telemetry_sync(self):
        """TC-G21-01: Verify Alpaca Paper account telemetry sync via GET /api/workbench/account?source=alpaca_paper."""
        r = requests.get(f"{API_BASE}/api/workbench/account?source=alpaca_paper", timeout=10)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "ACTIVE")
        self.assertEqual(data.get("currency"), "USD")
        self.assertEqual(data.get("data_source"), "ALPACA_PAPER")
        self.assertEqual(data.get("broker"), "ALPACA_PAPER")
        self.assertFalse(data.get("is_mock"))
        self.assertEqual(data.get("gate_status"), "CLOSED")
        # Cash balance consistency check ($99,773.38)
        self.assertEqual(data.get("cash"), 99773.38)
        self.assertGreater(data.get("buying_power", 0), 300000.0)

    def test_02_paper_positions_sync(self):
        """TC-G21-02: Verify Alpaca Paper open positions sync via GET /api/workbench/positions?source=alpaca_paper."""
        r = requests.get(f"{API_BASE}/api/workbench/positions?source=alpaca_paper", timeout=10)
        self.assertEqual(r.status_code, 200)
        positions = r.json()
        self.assertIsInstance(positions, list)
        self.assertGreaterEqual(len(positions), 2)
        symbols = [p["symbol"] for p in positions]
        self.assertIn("NVDA", symbols)
        self.assertTrue(any(s in ("BTCUSD", "BTC/USD") for s in symbols))
        for p in positions:
            self.assertEqual(p.get("data_source"), "ALPACA_PAPER")
            self.assertFalse(p.get("is_mock"))

    def test_03_paper_historical_orders_sync(self):
        """TC-G21-03: Verify Alpaca Paper historical orders sync via GET /api/workbench/orders?source=alpaca_paper."""
        r = requests.get(f"{API_BASE}/api/workbench/orders?source=alpaca_paper&limit=20", timeout=10)
        self.assertEqual(r.status_code, 200)
        orders = r.json()
        self.assertIsInstance(orders, list)
        self.assertGreaterEqual(len(orders), 2)
        order_ids = [o["id"] for o in orders]
        # Verify confirmed GĐ10/GĐ16 historical order IDs
        self.assertIn("25f85bed-b086-420a-87ab-52ea3d7a71ac", order_ids)
        self.assertIn("c5d4311a-2c15-441d-bc11-8a7384fe8eed", order_ids)
        for o in orders:
            self.assertEqual(o.get("data_source"), "ALPACA_PAPER")
            self.assertFalse(o.get("is_mock"))

    def test_04_paper_single_order_details(self):
        """TC-G21-04: Verify querying single Alpaca Paper order details via GET /api/paper/orders/{order_id}."""
        target_oid = "25f85bed-b086-420a-87ab-52ea3d7a71ac"
        r = requests.get(f"{API_BASE}/api/paper/orders/{target_oid}", timeout=10)
        self.assertEqual(r.status_code, 200)
        order = r.json()
        self.assertEqual(order.get("id"), target_oid)
        self.assertEqual(order.get("symbol"), "NVDA")
        self.assertEqual(order.get("side"), "buy")
        self.assertEqual(order.get("status"), "filled")
        self.assertEqual(order.get("filled_qty"), "1")
        self.assertEqual(order.get("filled_avg_price"), "216.8")
        self.assertEqual(order.get("data_source"), "ALPACA_PAPER")

    def test_05_paper_orders_filtering(self):
        """TC-G21-05: Verify symbol and side filtering on Alpaca Paper orders endpoint."""
        r_filtered = requests.get(f"{API_BASE}/api/workbench/orders?source=alpaca_paper&symbol=NVDA", timeout=10)
        self.assertEqual(r_filtered.status_code, 200)
        orders = r_filtered.json()
        for o in orders:
            self.assertEqual(o.get("symbol"), "NVDA")

    def test_06_unconfigured_credentials_handling(self):
        """TC-G21-06: Verify unconfigured credentials adapter behavior fails gracefully without throwing 500."""
        unconfigured_gate = AlpacaPaperGate(
            base_url="https://paper-api.alpaca.markets",
            key_id="",
            secret_key=""
        )
        acc = unconfigured_gate.get_account_overview()
        self.assertEqual(acc.get("status"), "UNCONFIGURED")
        pos = unconfigured_gate.get_positions()
        self.assertEqual(pos, [])
        ord_list = unconfigured_gate.get_orders()
        self.assertEqual(ord_list, [])

    def test_07_cash_balance_reconciliation(self):
        """TC-G21-07: Verify exact cash balance ($99,773.38) cross-reconciliation across all stages GĐ10–GĐ21."""
        r = requests.get(f"{API_BASE}/api/paper/account", timeout=10)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("cash"), 99773.38)

    # =========================================================================
    # GROUP 2: ORDER UPDATES VIA TRADINGSTREAM & EVENT PROCESSING (TC-G21-08 to TC-G21-14)
    # =========================================================================

    def test_08_trading_stream_event_ingestion(self):
        """TC-G21-08: Verify TradingStream event processor ingestion and cache update."""
        proc = AlpacaOrderStreamProcessor()
        test_oid = f"test_order_{uuid.uuid4().hex[:6]}"
        event_payload = {
            "event": "new",
            "timestamp": "2026-10-25T00:00:00Z",
            "order": {
                "id": test_oid,
                "symbol": "AAPL",
                "status": "new",
                "side": "buy",
                "qty": "5.0"
            }
        }
        res = proc.process_trade_update(event_payload)
        self.assertEqual(res.get("status"), "SUCCESS")
        cached = proc.get_order_state(test_oid)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.get("status"), "new")
        self.assertEqual(cached.get("symbol"), "AAPL")

    def test_09_stream_event_deduplication(self):
        """TC-G21-09: Verify duplicate TradingStream event detection and dropping."""
        proc = AlpacaOrderStreamProcessor()
        test_oid = "ord_dedup_test"
        event_payload = {
            "event": "fill",
            "timestamp": "2026-10-25T00:01:00Z",
            "order": {"id": test_oid, "symbol": "MSFT", "status": "filled", "filled_qty": "10"}
        }
        # First processing
        r1 = proc.process_trade_update(event_payload)
        self.assertEqual(r1.get("status"), "SUCCESS")

        # Second duplicate processing
        r2 = proc.process_trade_update(event_payload)
        self.assertEqual(r2.get("status"), "DROPPED_DUPLICATE")
        self.assertEqual(proc.metrics["duplicate_events_dropped"], 1)

    def test_10_out_of_order_state_precedence_protection(self):
        """TC-G21-10: Verify monotonic state precedence protects terminal 'filled' state against late 'new' events."""
        proc = AlpacaOrderStreamProcessor()
        test_oid = "ord_precedence_test"

        # 1. Advance to 'filled' terminal state
        proc.process_trade_update({
            "event": "fill",
            "timestamp": "2026-10-25T00:02:00Z",
            "order": {"id": test_oid, "status": "filled", "symbol": "NVDA"}
        })
        self.assertEqual(proc.get_order_state(test_oid).get("status"), "filled")

        # 2. Late-arriving 'new' event arrives later
        res = proc.process_trade_update({
            "event": "new",
            "timestamp": "2026-10-25T00:02:05Z",
            "order": {"id": test_oid, "status": "new", "symbol": "NVDA"}
        })
        self.assertEqual(res.get("status"), "HANDLED_OUT_OF_ORDER")
        # Ensure status was NOT reverted back to 'new'
        self.assertEqual(proc.get_order_state(test_oid).get("status"), "filled")
        self.assertEqual(proc.metrics["out_of_order_events_handled"], 1)

    def test_11_unknown_stream_event_handling(self):
        """TC-G21-11: Verify unknown trade update event types are isolated without crash."""
        proc = AlpacaOrderStreamProcessor()
        res = proc.process_trade_update({
            "event": "custom_broker_internal_event_xyz",
            "timestamp": "2026-10-25T00:03:00Z",
            "order": {"id": "ord_unknown_test", "symbol": "TSLA"}
        })
        self.assertEqual(res.get("status"), "RECORDED_UNKNOWN_EVENT")
        self.assertEqual(proc.metrics["unknown_events_handled"], 1)

    def test_12_disconnect_and_reconnect_tracking(self):
        """TC-G21-12: Verify connection status changes across disconnect and reconnect cycles."""
        proc = AlpacaOrderStreamProcessor()
        self.assertEqual(proc.connection_status, "CONNECTED")

        proc.simulate_disconnect()
        self.assertEqual(proc.connection_status, "DISCONNECTED")

        proc.reconnect()
        self.assertEqual(proc.connection_status, "CONNECTED")
        self.assertEqual(proc.reconnect_count, 1)

    def test_13_authoritative_rest_reconciliation(self):
        """TC-G21-13: Verify stream processor reconciles missed orders against authoritative REST snapshot."""
        proc = AlpacaOrderStreamProcessor()
        # In-memory stream cache initially empty
        self.assertEqual(len(proc.get_all_cached_orders()), 0)

        rest_orders = [
            {"id": "rest_ord_1", "symbol": "AAPL", "status": "filled", "qty": "10"},
            {"id": "rest_ord_2", "symbol": "NVDA", "status": "filled", "qty": "1"}
        ]
        recon = proc.reconcile_with_rest(rest_orders)
        self.assertEqual(recon.get("status"), "RECONCILED")
        self.assertEqual(recon.get("discrepancies_found"), 2)
        self.assertEqual(recon.get("synced_count"), 2)
        self.assertEqual(len(proc.get_all_cached_orders()), 2)

    def test_14_backend_stream_and_reconcile_endpoints(self):
        """TC-G21-14: Verify backend GET /api/paper/stream/status and /api/paper/sync/reconcile return 200 OK."""
        r_stream = requests.get(f"{API_BASE}/api/paper/stream/status", timeout=10)
        self.assertEqual(r_stream.status_code, 200)
        self.assertEqual(r_stream.json().get("connection_status"), "CONNECTED")

        r_recon = requests.get(f"{API_BASE}/api/paper/sync/reconcile", timeout=10)
        self.assertEqual(r_recon.status_code, 200)
        self.assertEqual(r_recon.json().get("status"), "RECONCILED")

    # =========================================================================
    # GROUP 3: PAPER EXECUTION GATE & SAFETY GUARDS (TC-G21-15 to TC-G21-26)
    # =========================================================================

    def test_15_paper_execution_gate_locked_by_default(self):
        """TC-G21-15: Verify submit_paper_order without fake_transport fails closed with PaperExecutionGateClosedError."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "AAPL", "side": "buy", "qty": 1.0})

    def test_16_paper_replacement_gate_locked(self):
        """TC-G21-16: Verify replace_paper_order without fake_transport fails closed."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.replace_paper_order("ord_test", {"qty": 2.0})

    def test_17_paper_cancel_gate_locked(self):
        """TC-G21-17: Verify cancel_paper_order without fake_transport fails closed."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.cancel_paper_order("ord_test")

    def test_18_paper_bulk_cancel_gate_locked(self):
        """TC-G21-18: Verify cancel_all_paper_orders without fake_transport fails closed."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.cancel_all_paper_orders()

    def test_19_safe_simulation_via_fake_transport(self):
        """TC-G21-19: Verify submit_paper_order with fake_transport=True performs validation with zero network calls."""
        gate = AlpacaPaperGate(is_gate_open=False)
        res = gate.submit_paper_order({
            "symbol": "NVDA",
            "side": "buy",
            "type": "limit",
            "qty": 5.0,
            "limit_price": 200.0
        }, fake_transport=True)
        self.assertEqual(res.get("status"), "fake_accepted")
        self.assertEqual(res.get("gate_status"), "CLOSED_MOCK_TRANSPORT")
        self.assertEqual(res.get("data_source"), "ALPACA_PAPER_FAKE")
        self.assertTrue(res.get("is_mock"))

    def test_20_live_endpoint_assertion_prevention(self):
        """TC-G21-20: Verify passing Live URL (api.alpaca.markets) raises LiveTradingProhibitedError immediately."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_21_backend_target_broker_paper_interceptor(self):
        """TC-G21-21: Verify POST /api/workbench/orders with target_broker='ALPACA_PAPER' returns HTTP 403 Forbidden."""
        payload = {
            "symbol": "AAPL",
            "side": "buy",
            "type": "market",
            "qty": 1.0,
            "target_broker": "ALPACA_PAPER"
        }
        r = requests.post(f"{API_BASE}/api/workbench/orders", json=payload, timeout=5)
        self.assertEqual(r.status_code, 403)
        self.assertIn("CRITICAL SAFETY GUARD", r.json().get("detail", ""))

    def test_22_server_side_safety_guards_maintained(self):
        """TC-G21-22: Verify server-side safety guards actively block legacy order routes with HTTP 403."""
        for ep in ["/api/orders", "/api/trade", "/api/v2/orders"]:
            r = requests.post(f"{API_BASE}{ep}", json={}, timeout=5)
            self.assertEqual(r.status_code, 403)

    def test_23_state_storage_segregation(self):
        """TC-G21-23: Verify strict storage segregation: mock broker state file does NOT contain Alpaca Paper orders."""
        state_file = os.path.join(BASE_DIR, "data", "mock_broker", "mock_broker_state.json")
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            orders = data.get("orders", {})
            # Ensure Alpaca Paper historical orders never leak into mock broker store
            self.assertNotIn("25f85bed-b086-420a-87ab-52ea3d7a71ac", orders)
            self.assertNotIn("c5d4311a-2c15-441d-bc11-8a7384fe8eed", orders)

    def test_24_dashboard_regression_integrity(self):
        """TC-G21-24: Verify non-regression of core dashboard endpoints."""
        endpoints = [
            "/api/health",
            "/api/system/status",
            "/api/paper/summary",
            "/api/crypto/candles?symbol=BTC/USD",
            "/api/crypto/signals"
        ]
        for ep in endpoints:
            r = requests.get(f"{API_BASE}{ep}", timeout=10)
            self.assertEqual(r.status_code, 200, f"Endpoint {ep} failed regression")

    def test_25_soak_runtime_preservation(self):
        """TC-G21-25: Verify ongoing GĐ18 soak session preservation (Flink jobs RUNNING 6/6 tasks)."""
        r_flink = requests.get(f"{FLINK_BASE}/jobs/overview", timeout=5)
        self.assertEqual(r_flink.status_code, 200)
        jobs = r_flink.json().get("jobs", [])
        running = [j for j in jobs if j.get("state") == "RUNNING" and j.get("tasks", {}).get("running") == 6]
        self.assertEqual(len(running), 2)

    def test_26_production_dry_run_immutability(self):
        """TC-G21-26: Verify TRADING_MODE=DRY_RUN remains immutable."""
        env_path = os.path.join(BASE_DIR, ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("TRADING_MODE=DRY_RUN", content)
        self.assertNotIn("TRADING_MODE=LIVE", content)


if __name__ == "__main__":
    unittest.main()

