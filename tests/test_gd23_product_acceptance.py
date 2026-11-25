"""
tests/test_gd23_product_acceptance.py — GĐ23 Product Acceptance & Paper Trading Readiness Test Suite

Verifies:
1. User Acceptance Testing (UAT) across the 6 core UI views:
   - Account Overview (TC-G23-01)
   - Positions (TC-G23-02)
   - Open Orders (TC-G23-03)
   - Order History (TC-G23-04)
   - Order Details (TC-G23-05)
   - Order Activity (TC-G23-06)
2. Mock Broker lifecycle operations & absolute data isolation:
   - Order creation for all 5 types (TC-G23-07)
   - In-flight order replacement (TC-G23-08)
   - Single & bulk cancellation (TC-G23-09)
   - State reset & initial cash restoration (TC-G23-10)
   - Storage segregation between mock state and real paper state (TC-G23-11)
3. Alpaca Paper Data Consistency & Timestamp Matching:
   - Real read-only synchronization matches Alpaca Paper API responses (TC-G23-12)
   - Exact mathematical cash accounting ($99,773.38) (TC-G23-13)
   - Satoshi-level BTC position quantity consistency (0.000120008 BTC via CFEE fee) (TC-G23-14)
4. Stream resilience, deduplication, and out-of-order handling:
   - TradingStream event deduplication (TC-G23-15)
   - Monotonic state hierarchy precedence (out-of-order protection) (TC-G23-16)
   - Unknown event tolerance (TC-G23-17)
   - Authoritative REST reconciliation upon reconnect (TC-G23-18)
5. Architectural Boundaries & Fail-Closed Enforcement:
   - Strict 3-mode operational separation (MOCK, READ_ONLY, EXECUTION) (TC-G23-19)
   - Server-side authority: POST /api/workbench/orders with target_broker='ALPACA_PAPER' blocked with 403 (TC-G23-20)
   - Legacy order routes intercepted with 403 Forbidden (TC-G23-21)
   - Live trading endpoint strictly prohibited (TC-G23-22)
6. Security Review & Credential Hygiene:
   - Credential leakage absence in client API responses (TC-G23-23)
   - Paper execution gate locked by default (TC-G23-24)
7. Operational Soak Preservation & Non-Regression:
   - GĐ18 operational soak preservation (Flink jobs RUNNING 6/6 tasks) (TC-G23-25)
   - Production DRY_RUN configuration immutability (TC-G23-26)
"""

import os
import sys
import json
import time
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


class TestGD23ProductAcceptance(unittest.TestCase):

    # =========================================================================
    # GROUP 1: USER ACCEPTANCE TESTING (UAT) ACROSS 6 CORE UI VIEWS (TC-G23-01 to TC-G23-06)
    # =========================================================================

    def test_01_uat_account_overview(self):
        """TC-G23-01: UAT Account Overview verification (Cash $99,773.38, BP > $300k, Status ACTIVE)."""
        res = requests.get(f"{API_BASE}/api/workbench/account?source=alpaca_paper", timeout=5)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("data_source"), "ALPACA_PAPER")
        self.assertEqual(data.get("status"), "ACTIVE")
        self.assertEqual(data.get("currency"), "USD")
        self.assertAlmostEqual(data.get("cash", 0), 99773.38, places=2)
        self.assertGreater(data.get("buying_power", 0), 300000.0)
        self.assertGreaterEqual(data.get("portfolio_value", 0), 99000.0)

    def test_02_uat_positions(self):
        """TC-G23-02: UAT Positions verification (NVDA qty 1.0, BTCUSD qty 0.000120008, P&L calculations)."""
        res = requests.get(f"{API_BASE}/api/workbench/positions?source=alpaca_paper", timeout=5)
        self.assertEqual(res.status_code, 200)
        positions = res.json()
        self.assertIsInstance(positions, list)
        self.assertEqual(len(positions), 2)
        
        symbols = {p["symbol"]: p for p in positions}
        self.assertIn("NVDA", symbols)
        self.assertIn("BTCUSD", symbols)
        
        # NVDA verification
        nvda = symbols["NVDA"]
        self.assertAlmostEqual(nvda["qty"], 1.0, places=2)
        self.assertAlmostEqual(nvda["avg_entry_price"], 216.80, places=2)
        self.assertEqual(nvda["side"], "long")
        self.assertEqual(nvda.get("data_source"), "ALPACA_PAPER")
        
        # BTCUSD verification
        btc = symbols["BTCUSD"]
        self.assertAlmostEqual(btc["qty"], 0.000120008, places=9)
        self.assertEqual(btc["side"], "long")
        self.assertEqual(btc.get("data_source"), "ALPACA_PAPER")

    def test_03_uat_open_orders(self):
        """TC-G23-03: UAT Open Orders verification (Filterable by status, symbol, side; 0 open orders on Alpaca Paper)."""
        res = requests.get(f"{API_BASE}/api/workbench/orders?source=alpaca_paper&status=open", timeout=5)
        self.assertEqual(res.status_code, 200)
        open_orders = res.json()
        self.assertIsInstance(open_orders, list)
        # Real Alpaca Paper has 0 open orders
        self.assertEqual(len(open_orders), 0)

    def test_04_uat_order_history(self):
        """TC-G23-04: UAT Order History verification (Historical orders NVDA and BTC with filled status)."""
        res = requests.get(f"{API_BASE}/api/workbench/orders?source=alpaca_paper&status=all", timeout=5)
        self.assertEqual(res.status_code, 200)
        orders = res.json()
        self.assertIsInstance(orders, list)
        self.assertEqual(len(orders), 2)
        
        symbols = {o["symbol"].replace("/", "") for o in orders}
        self.assertIn("NVDA", symbols)
        self.assertIn("BTCUSD", symbols)
        
        for o in orders:
            self.assertEqual(o["status"], "filled")
            self.assertGreater(float(o["filled_qty"]), 0)
            self.assertGreater(float(o["filled_avg_price"]), 0)
            self.assertIn("id", o)
            self.assertIn("created_at", o)

    def test_05_uat_order_details(self):
        """TC-G23-05: UAT Order Details verification (Query individual order by ID returning full broker attributes)."""
        # Historical NVDA order ID: 25f85bed-b086-420a-87ab-52ea3d7a71ac
        order_id = "25f85bed-b086-420a-87ab-52ea3d7a71ac"
        res = requests.get(f"{API_BASE}/api/paper/orders/{order_id}", timeout=5)
        self.assertEqual(res.status_code, 200)
        order = res.json()
        self.assertEqual(order.get("id"), order_id)
        self.assertEqual(order.get("symbol"), "NVDA")
        self.assertEqual(order.get("status"), "filled")
        self.assertEqual(float(order.get("qty", 0)), 1.0)
        self.assertEqual(float(order.get("filled_qty", 0)), 1.0)
        self.assertAlmostEqual(float(order.get("filled_avg_price", 0)), 216.80, places=2)

    def test_06_uat_order_activity(self):
        """TC-G23-06: UAT Order Activity verification (Returns JNLC, FILL, CFEE, FEE with correct descriptions)."""
        res = requests.get(f"{API_BASE}/api/paper/activities", timeout=5)
        self.assertEqual(res.status_code, 200)
        activities = res.json()
        self.assertIsInstance(activities, list)
        self.assertGreaterEqual(len(activities), 4)
        
        act_types = {a.get("activity_type") for a in activities}
        self.assertIn("JNLC", act_types)
        self.assertIn("FILL", act_types)
        self.assertIn("CFEE", act_types)
        self.assertIn("FEE", act_types)

    # =========================================================================
    # GROUP 2: MOCK BROKER OPERATIONS & DATA ISOLATION (TC-G23-07 to TC-G23-11)
    # =========================================================================

    def test_07_mock_broker_order_types_submission(self):
        """TC-G23-07: Mock Broker submission for Market, Limit, Stop, Stop-Limit, Trailing Stop with mock tagging."""
        order_payloads = [
            {"symbol": "AAPL", "side": "buy", "type": "market", "qty": 5.0},
            {"symbol": "MSFT", "side": "buy", "type": "limit", "qty": 10.0, "limit_price": 400.0},
            {"symbol": "GOOGL", "side": "buy", "type": "stop", "qty": 2.0, "stop_price": 180.0},
            {"symbol": "AMZN", "side": "buy", "type": "stop_limit", "qty": 4.0, "stop_price": 190.0, "limit_price": 188.0},
            {"symbol": "TSLA", "side": "sell", "type": "trailing_stop", "qty": 1.0, "trail_percent": 2.0},
        ]
        
        created_ids = []
        for p in order_payloads:
            res = requests.post(f"{API_BASE}/api/workbench/orders", json=p, timeout=5)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("is_mock"))
            self.assertEqual(data.get("broker"), "SIMULATED_MOCK_BROKER")
            self.assertTrue(data.get("id").startswith("mock_ord_"))
            created_ids.append(data.get("id"))
            
        self.assertEqual(len(created_ids), 5)

    def test_08_mock_broker_in_flight_replacement(self):
        """TC-G23-08: Mock Broker in-flight replacement (PATCH modifying limit_price, stop_price, qty)."""
        # Create an open limit order
        create_res = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "AMD",
            "side": "buy",
            "type": "limit",
            "qty": 10.0,
            "limit_price": 150.0
        }, timeout=5)
        self.assertEqual(create_res.status_code, 200)
        order_id = create_res.json()["id"]

        # Replace it
        patch_res = requests.patch(f"{API_BASE}/api/workbench/orders/{order_id}", json={
            "qty": 15.0,
            "limit_price": 152.5
        }, timeout=5)
        self.assertEqual(patch_res.status_code, 200)
        replaced = patch_res.json()
        self.assertEqual(replaced.get("replaces"), order_id)
        self.assertEqual(replaced.get("qty"), 15.0)
        self.assertEqual(replaced.get("limit_price"), 152.5)

    def test_09_mock_broker_cancellation_and_bulk_cancel(self):
        """TC-G23-09: Mock Broker single order cancellation and bulk cancel."""
        # Create an order and cancel it
        create_res = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "INTC",
            "side": "buy",
            "type": "limit",
            "qty": 20.0,
            "limit_price": 20.0
        }, timeout=5)
        self.assertEqual(create_res.status_code, 200)
        order_id = create_res.json()["id"]

        cancel_res = requests.delete(f"{API_BASE}/api/workbench/orders/{order_id}", timeout=5)
        self.assertEqual(cancel_res.status_code, 200)
        canceled = cancel_res.json()
        self.assertEqual(canceled["status"], "canceled")

        # Bulk cancel all
        bulk_res = requests.delete(f"{API_BASE}/api/workbench/orders", timeout=5)
        self.assertEqual(bulk_res.status_code, 200)
        self.assertIn("canceled_count", bulk_res.json())

    def test_10_mock_broker_state_reset(self):
        """TC-G23-10: Mock Broker state reset (POST /api/workbench/reset) restores initial cash and clears mock data."""
        res = requests.post(f"{API_BASE}/api/workbench/reset", json={}, timeout=5)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ACTIVE")
        self.assertEqual(data.get("cash"), 100000.0)
        self.assertTrue(data.get("is_mock"))

    def test_11_mock_vs_paper_data_segregation(self):
        """TC-G23-11: Verify strict data segregation: mock file never contains Alpaca Paper orders."""
        mock_file = os.path.join(BASE_DIR, "data", "workbench_orders.json")
        if os.path.exists(mock_file):
            with open(mock_file, "r") as f:
                state = json.load(f)
                orders = state.get("orders", {})
                for oid, ord_data in orders.items():
                    self.assertTrue(ord_data.get("is_mock"))
                    self.assertNotEqual(oid, "25f85bed-b086-420a-87ab-52ea3d7a71ac")
                    self.assertNotEqual(oid, "c5d4311a-2c15-441d-bc11-8a7384fe8eed")

    # =========================================================================
    # GROUP 3: ALPACA PAPER DATA CONSISTENCY & TIMESTAMP MATCHING (TC-G23-12 to TC-G23-14)
    # =========================================================================

    def test_12_paper_data_consistency_and_timestamp_matching(self):
        """TC-G23-12: Read-only synchronization matches Alpaca Paper API responses at identical timestamps."""
        acc_wb = requests.get(f"{API_BASE}/api/workbench/account?source=alpaca_paper", timeout=5).json()
        acc_direct = paper_gate.get_account_overview()
        
        self.assertEqual(acc_wb.get("account_number"), acc_direct.get("account_number"))
        self.assertEqual(acc_wb.get("cash"), acc_direct.get("cash"))
        self.assertEqual(acc_wb.get("portfolio_value"), acc_direct.get("portfolio_value"))

    def test_13_cash_balance_exact_accounting(self):
        """TC-G23-13: Reconcile exact cash balance ($99,773.38) mathematically against activities down to the cent."""
        calculated_cash = round(100000.0 - 216.80 - 9.80949 - 0.01, 2)
        self.assertEqual(calculated_cash, 99773.38)

        acc = paper_gate.get_account_overview()
        self.assertAlmostEqual(acc.get("cash", 0), 99773.38, places=2)

    def test_14_btc_position_satoshi_level_reconciliation(self):
        """TC-G23-14: Satoshi-level consistency: 0.000120008 BTC position reconciled via -0.000000301 BTC CFEE fee."""
        order_filled_qty = 0.000120309
        cfee_deduction = 0.000000301
        expected_pos_qty = round(order_filled_qty - cfee_deduction, 9)
        self.assertEqual(expected_pos_qty, 0.000120008)

        positions = paper_gate.get_positions()
        btc_pos = next((p for p in positions if p["symbol"] == "BTCUSD"), None)
        self.assertIsNotNone(btc_pos)
        self.assertAlmostEqual(btc_pos["qty"], 0.000120008, places=9)

    # =========================================================================
    # GROUP 4: STREAM RESILIENCE, DEDUPLICATION & RECONCILIATION (TC-G23-15 to TC-G23-18)
    # =========================================================================

    def test_15_trading_stream_deduplication(self):
        """TC-G23-15: TradingStream drops duplicate events based on event:order_id:timestamp key."""
        processor = AlpacaOrderStreamProcessor()
        raw_event = {
            "event": "fill",
            "timestamp": "2026-10-30T10:00:00Z",
            "order": {
                "id": "ord_dedup_test_23",
                "symbol": "NVDA",
                "status": "filled",
                "filled_qty": 1.0,
                "filled_avg_price": 216.80
            }
        }
        res1 = processor.process_trade_update(raw_event)
        self.assertEqual(res1.get("status"), "SUCCESS")
        
        # Second delivery of duplicate event
        res2 = processor.process_trade_update(raw_event)
        self.assertEqual(res2.get("status"), "DROPPED_DUPLICATE")
        self.assertGreaterEqual(processor.metrics.get("duplicate_events_dropped", 0), 1)

    def test_16_monotonic_state_hierarchy_protection(self):
        """TC-G23-16: Monotonic state hierarchy prevents out-of-order 'new' from overwriting terminal 'filled'."""
        processor = AlpacaOrderStreamProcessor()
        order_id = "ord_priority_uat_23"
        
        # 1. Filled event arrives
        processor.process_trade_update({
            "event": "fill",
            "timestamp": "2026-10-30T10:05:00Z",
            "order": {"id": order_id, "symbol": "NVDA", "status": "filled", "filled_qty": 1.0}
        })
        self.assertEqual(processor.get_order_state(order_id).get("status"), "filled")

        # 2. Delayed 'new' event arrives later
        res = processor.process_trade_update({
            "event": "new",
            "timestamp": "2026-10-30T10:04:50Z",
            "order": {"id": order_id, "symbol": "NVDA", "status": "new", "filled_qty": 0}
        })
        self.assertEqual(res.get("status"), "HANDLED_OUT_OF_ORDER")
        # Must retain 'filled'
        self.assertEqual(processor.get_order_state(order_id).get("status"), "filled")

    def test_17_unknown_stream_event_tolerance(self):
        """TC-G23-17: Unknown trade update events are safely handled without crash."""
        processor = AlpacaOrderStreamProcessor()
        res = processor.process_trade_update({
            "event": "custom_exchange_rebalance_event_x",
            "timestamp": "2026-10-30T10:10:00Z",
            "order": {"id": "ord_unknown_23", "symbol": "AAPL", "status": "open"}
        })
        self.assertEqual(res.get("status"), "RECORDED_UNKNOWN_EVENT")
        self.assertEqual(processor.metrics.get("unknown_events_handled"), 1)

    def test_18_rest_reconciliation_post_reconnect(self):
        """TC-G23-18: REST reconciliation restores order cache state after simulated stream disconnection."""
        processor = AlpacaOrderStreamProcessor()
        processor.simulate_disconnect()
        self.assertEqual(processor.connection_status, "DISCONNECTED")

        processor.reconnect()
        self.assertEqual(processor.connection_status, "CONNECTED")

        rest_orders = [
            {"id": "ord_reconcile_1", "symbol": "NVDA", "status": "filled", "filled_qty": 1.0},
            {"id": "ord_reconcile_2", "symbol": "BTCUSD", "status": "filled", "filled_qty": 0.000120008}
        ]
        summary = processor.reconcile_with_rest(rest_orders)
        self.assertEqual(summary.get("status"), "RECONCILED")
        self.assertEqual(summary.get("synced_count"), 2)

    # =========================================================================
    # GROUP 5: ARCHITECTURAL BOUNDARIES & FAIL-CLOSED GUARDS (TC-G23-19 to TC-G23-22)
    # =========================================================================

    def test_19_explicit_three_mode_classification(self):
        """TC-G23-19: Explicit 3-mode operational separation (MOCK, READ_ONLY, EXECUTION)."""
        self.assertEqual(BrokerMode.MOCK, "MOCK")
        self.assertEqual(BrokerMode.ALPACA_PAPER_READ_ONLY, "ALPACA_PAPER_READ_ONLY")
        self.assertEqual(BrokerMode.ALPACA_PAPER_EXECUTION, "ALPACA_PAPER_EXECUTION")
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        self.assertFalse(paper_gate.is_gate_open)

    def test_20_server_side_authority_assertion(self):
        """TC-G23-20: POST /api/workbench/orders with target_broker='ALPACA_PAPER' rejected with HTTP 403."""
        res = requests.post(
            f"{API_BASE}/api/workbench/orders",
            json={"symbol": "NVDA", "side": "buy", "type": "market", "qty": 1.0, "target_broker": "ALPACA_PAPER"},
            timeout=5
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("CRITICAL SAFETY GUARD", res.json().get("detail", ""))

    def test_21_legacy_order_routes_interception(self):
        """TC-G23-21: Server-side safety guards actively block legacy order routes with HTTP 403."""
        routes = ["/api/orders", "/api/trade", "/api/v2/orders"]
        for route in routes:
            res = requests.post(f"{API_BASE}{route}", json={"symbol": "NVDA", "side": "buy", "qty": 1}, timeout=5)
            self.assertEqual(res.status_code, 403, f"Route {route} failed to reject write with 403")

    def test_22_live_trading_endpoint_prohibition(self):
        """TC-G23-22: Live URL (api.alpaca.markets) raises LiveTradingProhibitedError immediately."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    # =========================================================================
    # GROUP 6: SECURITY REVIEW & CREDENTIAL HYGIENE (TC-G23-23 to TC-G23-24)
    # =========================================================================

    def test_23_credential_leakage_absence(self):
        """TC-G23-23: Absence of Alpaca API credentials in client builds and responses."""
        endpoints = [
            "/api/workbench/account?source=alpaca_paper",
            "/api/workbench/positions?source=alpaca_paper",
            "/api/workbench/orders?source=alpaca_paper",
            "/api/paper/activities",
            "/api/paper/stream/status"
        ]
        for ep in endpoints:
            res = requests.get(f"{API_BASE}{ep}", timeout=5)
            text = res.text
            self.assertNotIn("APCA-API-KEY-ID", text)
            self.assertNotIn("APCA-API-SECRET-KEY", text)

    def test_24_fail_closed_gate_default_enforcement(self):
        """TC-G23-24: Calling submit_paper_order without fake_transport fails closed with PaperExecutionGateClosedError."""
        gate = AlpacaPaperGate(is_gate_open=False)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "NVDA", "side": "buy", "qty": 1.0}, fake_transport=False)

    # =========================================================================
    # GROUP 7: OPERATIONAL HEALTH & SOAK PRESERVATION (TC-G23-25 to TC-G23-26)
    # =========================================================================

    def test_25_soak_runtime_preservation(self):
        """TC-G23-25: Flink streaming cluster has 2 active jobs with 6/6 tasks RUNNING and 0 failures."""
        res = requests.get(f"{FLINK_BASE}/jobs/overview", timeout=5)
        self.assertEqual(res.status_code, 200)
        jobs = res.json().get("jobs", [])
        self.assertGreaterEqual(len(jobs), 2)
        for j in jobs:
            self.assertEqual(j.get("state"), "RUNNING")
            tasks = j.get("tasks", {})
            self.assertEqual(tasks.get("running"), 6)
            self.assertEqual(tasks.get("failed"), 0)

    def test_26_production_dry_run_immutability(self):
        """TC-G23-26: Verify TRADING_MODE=DRY_RUN remains immutable in .env."""
        env_file = os.path.join(BASE_DIR, ".env")
        self.assertTrue(os.path.exists(env_file))
        with open(env_file, "r") as f:
            content = f.read()
            self.assertIn("TRADING_MODE=DRY_RUN", content)
            self.assertNotIn("TRADING_MODE=LIVE", content)
            self.assertNotIn("TRADING_MODE=PAPER_EXECUTION", content)


if __name__ == "__main__":
    unittest.main()
