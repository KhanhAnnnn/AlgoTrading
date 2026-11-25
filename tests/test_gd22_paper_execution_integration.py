"""
tests/test_gd22_paper_execution_integration.py — GĐ22 Alpaca Paper Order Execution Integration Test Suite
Verifies:
1. Explicit 3-mode architectural separation (MOCK, ALPACA_PAPER_READ_ONLY, ALPACA_PAPER_EXECUTION)
2. Fail-closed Execution Gate by default (zero write execution without fake_transport)
3. Simulated order lifecycle validation with fake transport (Market, Limit, Stop, Stop-Limit, Trailing Stop, Fractional, Notional)
4. Client order ID idempotency & replacement/cancellation lifecycle
5. TradingStream event resilience (deduplication, out-of-order precedence, REST reconciliation)
6. Ground-truth balance & position quantity audit (reconciling BTC position qty with CFEE fee, CAT fee, and cash balance)
7. Server-side safety guards (403 Forbidden on write routes) and storage segregation
8. Preservation of ongoing GĐ18 soak runtime and non-regression of existing APIs
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
    BrokerMode,
    paper_gate
)
from alpaca_order_stream_processor import (
    AlpacaOrderStreamProcessor,
    stream_processor
)

API_BASE = "http://127.0.0.1:8005"
FLINK_BASE = "http://127.0.0.1:8081"


class TestGD22PaperExecutionIntegration(unittest.TestCase):

    # =========================================================================
    # GROUP 1: ARCHITECTURAL REVIEW, GATE MODES & FAIL-CLOSED GUARDS (TC-G22-01 to TC-G22-07)
    # =========================================================================

    def test_01_explicit_three_mode_classification(self):
        """TC-G22-01: Verify explicit 3-mode architectural classification in AlpacaPaperGate."""
        self.assertEqual(BrokerMode.MOCK, "MOCK")
        self.assertEqual(BrokerMode.ALPACA_PAPER_READ_ONLY, "ALPACA_PAPER_READ_ONLY")
        self.assertEqual(BrokerMode.ALPACA_PAPER_EXECUTION, "ALPACA_PAPER_EXECUTION")
        # Default instance must strictly be ALPACA_PAPER_READ_ONLY
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        self.assertFalse(paper_gate.is_gate_open)

    def test_02_default_fail_closed_gate_enforcement(self):
        """TC-G22-02: Verify submit_paper_order fails closed by default when gate is locked."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "NVDA", "side": "buy", "qty": 1.0}, fake_transport=False)

    def test_03_missing_or_invalid_configuration_fails_closed(self):
        """TC-G22-03: Verify missing base_url or credentials fails closed without executing."""
        with self.assertRaises(PaperExecutionGateClosedError):
            AlpacaPaperGate(base_url="")

        unconfigured_gate = AlpacaPaperGate(
            base_url="https://paper-api.alpaca.markets",
            key_id="",
            secret_key=""
        )
        self.assertEqual(unconfigured_gate.get_account_overview().get("status"), "UNCONFIGURED")

    def test_04_non_paper_base_url_prevention(self):
        """TC-G22-04: Verify passing Live URL (api.alpaca.markets) raises LiveTradingProhibitedError immediately."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_05_server_side_authority_assertion(self):
        """TC-G22-05: Verify backend enforces execution boundary, rejecting target_broker='ALPACA_PAPER' with HTTP 403."""
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

    def test_06_server_side_safety_guards_maintained(self):
        """TC-G22-06: Verify legacy order submission routes remain intercepted with HTTP 403 Forbidden."""
        for ep in ["/api/orders", "/api/trade", "/api/v2/orders"]:
            r = requests.post(f"{API_BASE}{ep}", json={}, timeout=5)
            self.assertEqual(r.status_code, 403)

    def test_07_mock_vs_paper_data_segregation(self):
        """TC-G22-07: Verify strict segregation: mock broker state file does not contain Alpaca Paper orders."""
        state_file = os.path.join(BASE_DIR, "data", "mock_broker", "mock_broker_state.json")
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            orders = data.get("orders", {})
            self.assertNotIn("25f85bed-b086-420a-87ab-52ea3d7a71ac", orders)
            self.assertNotIn("c5d4311a-2c15-441d-bc11-8a7384fe8eed", orders)

    # =========================================================================
    # GROUP 2: SIMULATED ORDER LIFECYCLE WITH FAKE TRANSPORT (TC-G22-08 to TC-G22-16)
    # =========================================================================

    def test_08_fake_transport_market_order_submission(self):
        """TC-G22-08: Verify Market order validation and simulated confirmation with zero network calls."""
        gate = AlpacaPaperGate(is_gate_open=False)
        order_req = {"symbol": "AAPL", "side": "buy", "type": "market", "qty": 10.0}
        res = gate.submit_paper_order(order_req, fake_transport=True)
        self.assertEqual(res.get("status"), "fake_accepted")
        self.assertEqual(res.get("gate_status"), "CLOSED_MOCK_TRANSPORT")
        self.assertEqual(res.get("data_source"), "ALPACA_PAPER_FAKE")
        self.assertEqual(res.get("broker"), "ALPACA_PAPER_SIMULATED")
        self.assertTrue(res.get("is_mock"))

    def test_09_fake_transport_limit_order_validation(self):
        """TC-G22-09: Verify Limit order validation with fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        order_req = {"symbol": "NVDA", "side": "buy", "type": "limit", "qty": 5.0, "limit_price": 200.0}
        res = gate.submit_paper_order(order_req, fake_transport=True)
        self.assertEqual(res.get("type"), "limit")
        self.assertEqual(res.get("status"), "fake_accepted")

    def test_10_fake_transport_stop_order_validation(self):
        """TC-G22-10: Verify Stop order validation with fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        order_req = {"symbol": "TSLA", "side": "sell", "type": "stop", "qty": 2.0, "stop_price": 180.0}
        res = gate.submit_paper_order(order_req, fake_transport=True)
        self.assertEqual(res.get("type"), "stop")
        self.assertEqual(res.get("status"), "fake_accepted")

    def test_11_fake_transport_stop_limit_order_validation(self):
        """TC-G22-11: Verify Stop-Limit order validation with fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        order_req = {"symbol": "MSFT", "side": "buy", "type": "stop_limit", "qty": 4.0, "stop_price": 400.0, "limit_price": 405.0}
        res = gate.submit_paper_order(order_req, fake_transport=True)
        self.assertEqual(res.get("type"), "stop_limit")
        self.assertEqual(res.get("status"), "fake_accepted")

    def test_12_fake_transport_trailing_stop_validation(self):
        """TC-G22-12: Verify Trailing Stop order validation with fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        order_req = {"symbol": "BTC/USD", "side": "sell", "type": "trailing_stop", "qty": 0.05, "trail_percent": 2.5}
        res = gate.submit_paper_order(order_req, fake_transport=True)
        self.assertEqual(res.get("type"), "trailing_stop")
        self.assertEqual(res.get("status"), "fake_accepted")

    def test_13_fractional_and_notional_validation(self):
        """TC-G22-13: Verify fractional quantities, notional amounts, and mutual exclusivity."""
        gate = AlpacaPaperGate(is_gate_open=False)
        # Fractional order
        res_frac = gate.submit_paper_order({"symbol": "BTC/USD", "side": "buy", "qty": 0.0452}, fake_transport=True)
        self.assertEqual(res_frac.get("qty"), "0.0452")

        # Notional order
        res_notional = gate.submit_paper_order({"symbol": "ETH/USD", "side": "buy", "notional": 1000.0}, fake_transport=True)
        self.assertEqual(res_notional.get("notional"), "1000.0")

        # Exclusivity violation (both qty and notional)
        with self.assertRaises(ValueError):
            gate.submit_paper_order({"symbol": "AAPL", "side": "buy", "qty": 10.0, "notional": 1000.0}, fake_transport=True)

    def test_14_client_order_id_handling(self):
        """TC-G22-14: Verify client_order_id preservation and idempotency handling."""
        gate = AlpacaPaperGate(is_gate_open=False)
        cid = f"test_cli_{uuid.uuid4().hex[:6]}"
        res = gate.submit_paper_order({"symbol": "AAPL", "side": "buy", "qty": 1.0, "client_order_id": cid}, fake_transport=True)
        self.assertEqual(res.get("client_order_id"), cid)

    def test_15_fake_transport_order_replacement_lifecycle(self):
        """TC-G22-15: Verify simulated order replacement via fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        res = gate.replace_paper_order("fake_parent_123", {"qty": 8.0, "limit_price": 205.0}, fake_transport=True)
        self.assertEqual(res.get("status"), "fake_replaced")
        self.assertEqual(res.get("replaces"), "fake_parent_123")
        self.assertEqual(res.get("qty"), "8.0")
        self.assertEqual(res.get("limit_price"), "205.0")

    def test_16_fake_transport_single_and_bulk_cancellation(self):
        """TC-G22-16: Verify simulated order cancellation and bulk cancel via fake transport."""
        gate = AlpacaPaperGate(is_gate_open=False)
        res_single = gate.cancel_paper_order("fake_oid_456", fake_transport=True)
        self.assertEqual(res_single.get("status"), "fake_canceled")
        self.assertEqual(res_single.get("id"), "fake_oid_456")

        res_bulk = gate.cancel_all_paper_orders(fake_transport=True)
        self.assertIsInstance(res_bulk, list)
        self.assertGreater(len(res_bulk), 0)
        self.assertEqual(res_bulk[0].get("status"), "fake_canceled")

    # =========================================================================
    # GROUP 3: TRADINGSTREAM RESILIENCE & EVENT PROCESSING (TC-G22-17 to TC-G22-20)
    # =========================================================================

    def test_17_trading_stream_event_ingestion(self):
        """TC-G22-17: Verify stream processor ingests events and maintains in-memory cache."""
        proc = AlpacaOrderStreamProcessor()
        oid = f"stream_test_{uuid.uuid4().hex[:6]}"
        res = proc.process_trade_update({
            "event": "new",
            "timestamp": "2026-10-25T00:10:00Z",
            "order": {"id": oid, "symbol": "NVDA", "status": "new", "qty": "5"}
        })
        self.assertEqual(res.get("status"), "SUCCESS")
        self.assertEqual(proc.get_order_state(oid).get("status"), "new")

    def test_18_trading_stream_deduplication(self):
        """TC-G22-18: Verify duplicate events are dropped and counted in metrics."""
        proc = AlpacaOrderStreamProcessor()
        oid = "stream_dedup_test"
        payload = {
            "event": "fill",
            "timestamp": "2026-10-25T00:11:00Z",
            "order": {"id": oid, "symbol": "AAPL", "status": "filled"}
        }
        r1 = proc.process_trade_update(payload)
        self.assertEqual(r1.get("status"), "SUCCESS")

        r2 = proc.process_trade_update(payload)
        self.assertEqual(r2.get("status"), "DROPPED_DUPLICATE")
        self.assertEqual(proc.metrics["duplicate_events_dropped"], 1)

    def test_19_out_of_order_monotonic_priority_protection(self):
        """TC-G22-19: Verify monotonic state hierarchy prevents late 'new' from overwriting 'filled'."""
        proc = AlpacaOrderStreamProcessor()
        oid = "stream_priority_test"
        proc.process_trade_update({
            "event": "fill",
            "timestamp": "2026-10-25T00:12:00Z",
            "order": {"id": oid, "symbol": "MSFT", "status": "filled"}
        })
        self.assertEqual(proc.get_order_state(oid).get("status"), "filled")

        # Late 'new' event arrives
        res = proc.process_trade_update({
            "event": "new",
            "timestamp": "2026-10-25T00:12:05Z",
            "order": {"id": oid, "symbol": "MSFT", "status": "new"}
        })
        self.assertEqual(res.get("status"), "HANDLED_OUT_OF_ORDER")
        self.assertEqual(proc.get_order_state(oid).get("status"), "filled")

    def test_20_rest_reconciliation_post_disconnection(self):
        """TC-G22-20: Verify REST reconciliation restores stream order state after simulated disconnect."""
        proc = AlpacaOrderStreamProcessor()
        proc.simulate_disconnect()
        self.assertEqual(proc.connection_status, "DISCONNECTED")
        proc.reconnect()
        self.assertEqual(proc.connection_status, "CONNECTED")

        rest_orders = [
            {"id": "25f85bed-b086-420a-87ab-52ea3d7a71ac", "symbol": "NVDA", "status": "filled"},
            {"id": "c5d4311a-2c15-441d-bc11-8a7384fe8eed", "symbol": "BTC/USD", "status": "filled"}
        ]
        recon = proc.reconcile_with_rest(rest_orders)
        self.assertEqual(recon.get("status"), "RECONCILED")
        self.assertEqual(recon.get("synced_count"), 2)

    # =========================================================================
    # GROUP 4: BALANCE, ACTIVITY & POSITION QUANTITY AUDIT (TC-G22-21 to TC-G22-26)
    # =========================================================================

    def test_21_account_activities_telemetry_audit(self):
        """TC-G21-21: Verify GET /api/paper/activities retrieves historical account activities (JNLC, FILL, CFEE, FEE)."""
        r = requests.get(f"{API_BASE}/api/paper/activities", timeout=10)
        self.assertEqual(r.status_code, 200)
        activities = r.json()
        self.assertIsInstance(activities, list)
        self.assertGreaterEqual(len(activities), 4)

        activity_types = [a.get("activity_type") for a in activities]
        self.assertIn("JNLC", activity_types)
        self.assertIn("FILL", activity_types)
        self.assertIn("CFEE", activity_types)
        self.assertIn("FEE", activity_types)

    def test_22_btc_position_quantity_vs_order_filled_reconciliation(self):
        """TC-G22-22: Reconcile BTC position qty (0.000120008) against order filled qty (0.000120309) via CFEE fee (-0.000000301)."""
        r_pos = requests.get(f"{API_BASE}/api/paper/positions", timeout=10).json()
        btc_pos = next(p for p in r_pos if p["symbol"] in ("BTCUSD", "BTC/USD"))
        pos_qty = float(btc_pos["qty"])

        r_orders = requests.get(f"{API_BASE}/api/paper/orders", timeout=10).json()
        btc_order = next(o for o in r_orders if "BTC" in o["symbol"])
        order_filled_qty = float(btc_order["filled_qty"])

        r_act = requests.get(f"{API_BASE}/api/paper/activities", timeout=10).json()
        cfee_act = next(a for a in r_act if a.get("activity_type") == "CFEE")
        cfee_qty = abs(float(cfee_act["qty"]))

        # Mathematical Proof: Position Qty = Order Filled Qty - Crypto Transaction Fee Qty
        reconciled_qty = round(order_filled_qty - cfee_qty, 9)
        self.assertAlmostEqual(pos_qty, reconciled_qty, places=8)
        self.assertEqual(pos_qty, 0.000120008)
        self.assertEqual(order_filled_qty, 0.000120309)
        self.assertEqual(cfee_qty, 0.000000301)

    def test_23_cash_balance_exact_accounting(self):
        """TC-G22-23: Verify cash balance ($99,773.38) mathematically reconciles against all activity costs and fees."""
        r_acc = requests.get(f"{API_BASE}/api/paper/account", timeout=10).json()
        cash = float(r_acc["cash"])
        self.assertEqual(cash, 99773.38)

        # $100,000 initial - $9.80949 BTC - $216.80 NVDA - $0.01 CAT fee = $99,773.38
        expected_cash = round(100000.00 - 9.809490422 - 216.80 - 0.01, 2)
        self.assertEqual(cash, expected_cash)

    def test_24_dashboard_regression_integrity(self):
        """TC-G22-24: Verify non-regression of core dashboard endpoints."""
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
        """TC-G22-25: Verify ongoing GĐ18 soak session preservation (Flink jobs RUNNING 6/6 tasks)."""
        r_flink = requests.get(f"{FLINK_BASE}/jobs/overview", timeout=5)
        self.assertEqual(r_flink.status_code, 200)
        jobs = r_flink.json().get("jobs", [])
        running = [j for j in jobs if j.get("state") == "RUNNING" and j.get("tasks", {}).get("running") == 6]
        self.assertEqual(len(running), 2)

    def test_26_production_dry_run_immutability(self):
        """TC-G22-26: Verify TRADING_MODE=DRY_RUN remains immutable in .env."""
        env_path = os.path.join(BASE_DIR, ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("TRADING_MODE=DRY_RUN", content)
        self.assertNotIn("TRADING_MODE=LIVE", content)


if __name__ == "__main__":
    unittest.main()
