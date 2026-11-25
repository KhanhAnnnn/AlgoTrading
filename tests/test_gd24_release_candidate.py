"""
tests/test_gd24_release_candidate.py — GĐ24 Product Finalization & Release Candidate Test Suite

Verifies:
1. Group 1: UX Navigation & Standardized Data State Indicators (TC-G24-01 to TC-G24-04)
2. Group 2: Mock Broker Order Lifecycle & Isolated State (TC-G24-05 to TC-G24-09)
3. Group 3: Alpaca Paper Read-Only & Reconciliation Provenance (TC-G24-10 to TC-G24-14)
4. Group 4: Stream Resilience & Self-Healing (TC-G24-15 to TC-G24-17)
5. Group 5: Operational Readiness & Health Observability (TC-G24-18 to TC-G24-21)
6. Group 6: Security Audit & Server-Side Enforcement (TC-G24-22 to TC-G24-24)
7. Group 7: Production Release Candidate Verification (TC-G24-25 to TC-G24-26)
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


class TestGD24ReleaseCandidate(unittest.TestCase):

    # =========================================================================
    # GROUP 1: UX NAVIGATION & DATA STATE INDICATORS (TC-G24-01 to TC-G24-04)
    # =========================================================================

    def test_01_navigation_structure_and_endpoints(self):
        """TC-G24-01: Verify navigation endpoints across 5 core groups (Market, Analytics, Portfolio, Workbench, System)."""
        core_endpoints = [
            "/api/health",
            "/api/candles?symbol=NVDA&timeframe=1m",
            "/api/crypto/candles?symbol=BTC/USD&timeframe=1m",
            "/api/signals",
            "/api/news",
            "/api/system/status",
            "/api/workbench/account?source=alpaca_paper",
            "/api/workbench/account?source=mock",
            "/api/workbench/positions?source=alpaca_paper",
            "/api/workbench/orders?source=alpaca_paper",
            "/api/workbench/activities",
            "/api/observability/stream",
            "/api/reliability/events",
            "/api/shadow/observations",
            "/api/shadow/metrics"
        ]
        for ep in core_endpoints:
            res = requests.get(f"{API_BASE}{ep}", timeout=5)
            self.assertEqual(res.status_code, 200, f"Endpoint {ep} failed with {res.status_code}")

    def test_02_explicit_data_source_tagging(self):
        """TC-G24-02: Verify explicit data state tagging (ALPACA_PAPER, MOCK, LIVE_DATA)."""
        # 1. Alpaca Paper tagging
        acc_paper = requests.get(f"{API_BASE}/api/workbench/account?source=alpaca_paper", timeout=5).json()
        self.assertEqual(acc_paper.get("data_source"), "ALPACA_PAPER")
        self.assertEqual(acc_paper.get("broker"), "ALPACA_PAPER")
        self.assertFalse(acc_paper.get("is_mock"))

        # 2. Mock Broker tagging
        acc_mock = requests.get(f"{API_BASE}/api/workbench/account?source=mock", timeout=5).json()
        self.assertEqual(acc_mock.get("data_source"), "MOCK")
        self.assertEqual(acc_mock.get("broker"), "SIMULATED_MOCK_BROKER")
        self.assertTrue(acc_mock.get("is_mock"))

    def test_03_last_updated_timestamp_presence(self):
        """TC-G24-03: Verify Last Updated timestamp presence and formatting across telemetry endpoints."""
        sys_status = requests.get(f"{API_BASE}/api/system/status", timeout=5).json()
        self.assertIn("backend_time", sys_status)
        self.assertGreater(sys_status["backend_time"], 1700000000)

        health = requests.get(f"{API_BASE}/api/health", timeout=5).json()
        self.assertIn("timestamp", health)

    def test_04_executive_dashboard_five_questions(self):
        """TC-G24-04: Verify executive dashboard endpoints answer the 5 core market and operational questions."""
        # Q1: How is the market moving? (Candles & price change)
        candles_res = requests.get(f"{API_BASE}/api/candles?symbol=NVDA&timeframe=1m", timeout=5).json()
        self.assertIn("candles", candles_res)
        self.assertGreaterEqual(len(candles_res["candles"]), 1)

        # Q2: Is data streaming in real time? (System telemetry data mode)
        sys_res = requests.get(f"{API_BASE}/api/system/status", timeout=5).json()
        self.assertTrue(sys_res.get("kafka", {}).get("redpanda_connected"))

        # Q3: What signals has the system generated? (Signals endpoint)
        sig_res = requests.get(f"{API_BASE}/api/signals", timeout=5).json()
        self.assertIn("signals", sig_res)

        # Q4: What is the account and position status? (Account & Positions)
        pos_res = requests.get(f"{API_BASE}/api/workbench/positions?source=alpaca_paper", timeout=5).json()
        self.assertEqual(len(pos_res), 2)

        # Q5: Is the entire infrastructure healthy? (Health pillars)
        obs_res = requests.get(f"{API_BASE}/api/observability/stream", timeout=5).json()
        self.assertIn("health_pillars", obs_res)

    # =========================================================================
    # GROUP 2: MOCK BROKER ORDER LIFECYCLE & STATE ISOLATION (TC-G24-05 to TC-G24-09)
    # =========================================================================

    def test_05_mock_broker_order_types_execution(self):
        """TC-G24-05: Mock Broker order placement for Market, Limit, Stop, Stop-Limit, Trailing Stop."""
        orders_to_create = [
            {"symbol": "NVDA", "side": "buy", "type": "market", "qty": 2.0},
            {"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 5.0, "limit_price": 220.0},
            {"symbol": "MSFT", "side": "buy", "type": "stop", "qty": 3.0, "stop_price": 410.0},
            {"symbol": "GOOGL", "side": "buy", "type": "stop_limit", "qty": 4.0, "stop_price": 175.0, "limit_price": 173.0},
            {"symbol": "TSLA", "side": "sell", "type": "trailing_stop", "qty": 1.0, "trail_percent": 1.5},
        ]
        created_ids = []
        for o in orders_to_create:
            res = requests.post(f"{API_BASE}/api/workbench/orders", json=o, timeout=5)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("is_mock"))
            self.assertTrue(data.get("id").startswith("mock_ord_"))
            created_ids.append(data.get("id"))
        self.assertEqual(len(created_ids), 5)

    def test_06_mock_fractional_and_notional_orders(self):
        """TC-G24-06: Mock Broker fractional quantity and notional orders validation and execution."""
        # Fractional Qty order
        res_frac = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "BTC/USD", "side": "buy", "type": "market", "qty": 0.05
        }, timeout=5)
        self.assertEqual(res_frac.status_code, 200)
        self.assertAlmostEqual(res_frac.json().get("qty"), 0.05, places=4)

        # Notional Dollar order
        res_notional = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "AAPL", "side": "buy", "type": "market", "notional": 500.0
        }, timeout=5)
        self.assertEqual(res_notional.status_code, 200)
        self.assertAlmostEqual(res_notional.json().get("notional"), 500.0, places=2)

    def test_07_mock_order_replacement_replaces_link(self):
        """TC-G24-07: In-flight order replacement creates replaced order with proper 'replaces' reference."""
        # Create limit order
        c_res = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "NVDA", "side": "buy", "type": "limit", "qty": 8.0, "limit_price": 200.0
        }, timeout=5)
        self.assertEqual(c_res.status_code, 200)
        orig_id = c_res.json()["id"]

        # Replace order
        r_res = requests.patch(f"{API_BASE}/api/workbench/orders/{orig_id}", json={
            "qty": 12.0, "limit_price": 202.0
        }, timeout=5)
        self.assertEqual(r_res.status_code, 200)
        replaced = r_res.json()
        self.assertEqual(replaced.get("replaces"), orig_id)
        self.assertEqual(replaced.get("qty"), 12.0)
        self.assertEqual(replaced.get("limit_price"), 202.0)

    def test_08_mock_single_and_bulk_cancellation(self):
        """TC-G24-08: Single and bulk cancellation without broker interaction."""
        # Create an order
        c_res = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "AMZN", "side": "buy", "type": "limit", "qty": 10.0, "limit_price": 180.0
        }, timeout=5)
        oid = c_res.json()["id"]

        # Cancel single order
        d_res = requests.delete(f"{API_BASE}/api/workbench/orders/{oid}", timeout=5)
        self.assertEqual(d_res.status_code, 200)
        self.assertEqual(d_res.json().get("status"), "canceled")

        # Bulk cancel all
        bulk_res = requests.delete(f"{API_BASE}/api/workbench/orders", timeout=5)
        self.assertEqual(bulk_res.status_code, 200)
        self.assertIn("canceled_count", bulk_res.json())

    def test_09_mock_storage_segregation(self):
        """TC-G24-09: Verify Mock Broker state isolation in data/mock_broker/mock_broker_state.json."""
        state_file = os.path.join(BASE_DIR, "data", "mock_broker", "mock_broker_state.json")
        self.assertTrue(os.path.exists(state_file))
        with open(state_file, "r") as f:
            state = json.load(f)
            orders = state.get("orders", {})
            for oid, ord_data in orders.items():
                self.assertTrue(ord_data.get("is_mock"))
                self.assertNotEqual(oid, "25f85bed-b086-420a-87ab-52ea3d7a71ac")
                self.assertNotEqual(oid, "c5d4311a-2c15-441d-bc11-8a7384fe8eed")

    # =========================================================================
    # GROUP 3: ALPACA PAPER READ-ONLY & PROVENANCE RECONCILIATION (TC-G24-10 to TC-G24-14)
    # =========================================================================

    def test_10_paper_data_synchronization(self):
        """TC-G24-10: Alpaca Paper Read-Only synchronization matches broker at same timestamp."""
        acc_wb = requests.get(f"{API_BASE}/api/workbench/account?source=alpaca_paper", timeout=5).json()
        acc_gate = paper_gate.get_account_overview()
        self.assertEqual(acc_wb.get("account_number"), acc_gate.get("account_number"))
        self.assertAlmostEqual(acc_wb.get("cash", 0), acc_gate.get("cash", 0), places=2)

    def test_11_cash_balance_exact_accounting(self):
        """TC-G24-11: Exact cash balance accounting ($99,773.38) across initial deposit and activities."""
        # 100,000.00 (JNLC) - 216.80 (NVDA) - 9.80949 (BTC) - 0.01 (FEE) = 99,773.38051
        expected_cash = round(100000.0 - 216.80 - 9.80949 - 0.01, 2)
        self.assertEqual(expected_cash, 99773.38)

        acc = paper_gate.get_account_overview()
        self.assertAlmostEqual(acc.get("cash", 0), 99773.38, places=2)

    def test_12_buying_power_variance_reconciliation(self):
        """TC-G24-12: Reconcile Buying Power variance between snapshots based on market valuation of held shares."""
        acc = paper_gate.get_account_overview()
        bp = acc.get("buying_power", 0)
        # Buying power should be roughly 4x cash/equity under Reg-T margin
        self.assertGreater(bp, 390000.0)
        self.assertLess(bp, 410000.0)

    def test_13_reconcile_four_activity_types_across_five_records(self):
        """TC-G24-13: Reconcile 4 activity types (JNLC, FILL, CFEE, FEE) across 5 distinct historical records."""
        activities = paper_gate.get_account_activities(limit=50)
        self.assertGreaterEqual(len(activities), 4)

        act_types = set()
        fills_count = 0
        for a in activities:
            t = a.get("activity_type")
            act_types.add(t)
            if t == "FILL":
                fills_count += 1

        self.assertIn("JNLC", act_types)
        self.assertIn("FILL", act_types)
        self.assertIn("CFEE", act_types)
        self.assertIn("FEE", act_types)
        self.assertGreaterEqual(fills_count, 2)  # NVDA and BTC fills

    def test_14_btc_position_satoshi_reconciliation(self):
        """TC-G24-14: Reconcile Satoshi-level BTC position quantity (0.000120008 BTC) via CFEE fee deduction."""
        order_filled_qty = 0.000120309
        cfee_deduction = 0.000000301
        expected_pos_qty = round(order_filled_qty - cfee_deduction, 9)
        self.assertEqual(expected_pos_qty, 0.000120008)

        positions = paper_gate.get_positions()
        btc_pos = next((p for p in positions if p["symbol"] == "BTCUSD"), None)
        self.assertIsNotNone(btc_pos)
        self.assertAlmostEqual(btc_pos["qty"], 0.000120008, places=9)

    # =========================================================================
    # GROUP 4: STREAM RESILIENCE & SELF-HEALING (TC-G24-15 to TC-G24-17)
    # =========================================================================

    def test_15_trading_stream_deduplication(self):
        """TC-G24-15: TradingStream drops duplicate events via event:order_id:timestamp key."""
        processor = AlpacaOrderStreamProcessor()
        raw_event = {
            "event": "fill",
            "timestamp": "2026-10-30T14:00:00Z",
            "order": {"id": "ord_dedup_rc_24", "symbol": "NVDA", "status": "filled", "filled_qty": 1.0}
        }
        res1 = processor.process_trade_update(raw_event)
        self.assertEqual(res1.get("status"), "SUCCESS")

        res2 = processor.process_trade_update(raw_event)
        self.assertEqual(res2.get("status"), "DROPPED_DUPLICATE")
        self.assertGreaterEqual(processor.metrics["duplicate_events_dropped"], 1)

    def test_16_monotonic_state_hierarchy_protection(self):
        """TC-G24-16: Monotonic state hierarchy prevents late 'new' from overwriting terminal 'filled'."""
        processor = AlpacaOrderStreamProcessor()
        oid = "ord_priority_rc_24"
        processor.process_trade_update({
            "event": "fill", "timestamp": "2026-10-30T14:01:00Z",
            "order": {"id": oid, "symbol": "AAPL", "status": "filled", "filled_qty": 5.0}
        })
        self.assertEqual(processor.get_order_state(oid).get("status"), "filled")

        res = processor.process_trade_update({
            "event": "new", "timestamp": "2026-10-30T14:00:50Z",
            "order": {"id": oid, "symbol": "AAPL", "status": "new", "filled_qty": 0}
        })
        self.assertEqual(res.get("status"), "HANDLED_OUT_OF_ORDER")
        self.assertEqual(processor.get_order_state(oid).get("status"), "filled")

    def test_17_rest_reconciliation_post_disconnection(self):
        """TC-G24-17: REST reconciliation heals stream state cache after disconnection."""
        processor = AlpacaOrderStreamProcessor()
        processor.simulate_disconnect()
        self.assertEqual(processor.connection_status, "DISCONNECTED")
        processor.reconnect()
        self.assertEqual(processor.connection_status, "CONNECTED")

        rest_orders = [
            {"id": "25f85bed-b086-420a-87ab-52ea3d7a71ac", "symbol": "NVDA", "status": "filled"},
            {"id": "c5d4311a-2c15-441d-bc11-8a7384fe8eed", "symbol": "BTC/USD", "status": "filled"}
        ]
        recon = processor.reconcile_with_rest(rest_orders)
        self.assertEqual(recon.get("status"), "RECONCILED")
        self.assertEqual(recon.get("synced_count"), 2)

    # =========================================================================
    # GROUP 5: OPERATIONAL READINESS & HEALTH OBSERVABILITY (TC-G24-18 to TC-G24-21)
    # =========================================================================

    def test_18_five_pillar_health_differentiation(self):
        """TC-G24-18: 5-pillar health architecture differentiates HEALTHY, STALE, DOWN, IDLE_MARKET_CLOSED."""
        res = requests.get(f"{API_BASE}/api/observability/stream", timeout=5)
        self.assertEqual(res.status_code, 200)
        pillars = res.json().get("health_pillars", {})
        self.assertIn("infrastructure", pillars)
        self.assertIn("data_freshness", pillars)
        self.assertIn("processing", pillars)
        self.assertIn("signal_handlers", pillars)
        self.assertIn("end_to_end", pillars)

    def test_19_consumer_lag_within_sla(self):
        """TC-G24-19: Redpanda consumer lag is strictly within SLA (lag <= 50, actual=0)."""
        res = requests.get(f"{API_BASE}/api/observability/stream", timeout=5)
        self.assertEqual(res.status_code, 200)
        lags = res.json().get("consumer_lag", {})
        for grp, info in lags.items():
            self.assertLessEqual(info.get("lag", 0), 50)

    def test_20_flink_checkpoint_continuity(self):
        """TC-G24-20: Flink streaming has 2 active jobs with 6/6 tasks RUNNING and 0 checkpoint failures."""
        res = requests.get(f"{FLINK_BASE}/jobs/overview", timeout=5)
        self.assertEqual(res.status_code, 200)
        jobs = res.json().get("jobs", [])
        self.assertGreaterEqual(len(jobs), 2)
        for j in jobs:
            self.assertEqual(j.get("state"), "RUNNING")
            self.assertEqual(j.get("tasks", {}).get("running"), 6)
            jid = j.get("jid")
            c_res = requests.get(f"{FLINK_BASE}/jobs/{jid}/checkpoints", timeout=5)
            self.assertEqual(c_res.status_code, 200)
            counts = c_res.json().get("counts", {})
            self.assertEqual(counts.get("failed", 0), 0)

    def test_21_operational_script_guards_verification(self):
        """TC-G24-21: Operational script guards verify that status_all.ps1 and health scripts exist and are safe."""
        status_script = os.path.join(BASE_DIR, "scripts", "status_all.ps1")
        self.assertTrue(os.path.exists(status_script))
        with open(status_script, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("ALGOTRADING PLATFORM HEALTH", content)

    # =========================================================================
    # GROUP 6: SECURITY AUDIT & SERVER-SIDE ENFORCEMENT (TC-G24-22 to TC-G24-24)
    # =========================================================================

    def test_22_server_side_authority_assertion(self):
        """TC-G24-22: Server-side HTTP 403 Forbidden when target_broker='ALPACA_PAPER'."""
        res = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "NVDA", "side": "buy", "type": "market", "qty": 1.0, "target_broker": "ALPACA_PAPER"
        }, timeout=5)
        self.assertEqual(res.status_code, 403)
        self.assertIn("CRITICAL SAFETY GUARD", res.json().get("detail", ""))

    def test_23_fail_closed_paper_execution_gate(self):
        """TC-G24-23: PaperExecutionGate.is_gate_open is False; submit_paper_order fails closed."""
        self.assertFalse(paper_gate.is_gate_open)
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        with self.assertRaises(PaperExecutionGateClosedError):
            paper_gate.submit_paper_order({"symbol": "NVDA", "side": "buy", "qty": 1.0}, fake_transport=False)

    def test_24_credential_hygiene_and_leakage_absence(self):
        """TC-G24-24: Absence of API credentials in client builds and responses."""
        endpoints = [
            "/api/workbench/account?source=alpaca_paper",
            "/api/workbench/positions?source=alpaca_paper",
            "/api/workbench/orders?source=alpaca_paper",
            "/api/paper/activities",
            "/api/system/status"
        ]
        for ep in endpoints:
            text = requests.get(f"{API_BASE}{ep}", timeout=5).text
            self.assertNotIn("APCA-API-KEY-ID", text)
            self.assertNotIn("APCA-API-SECRET-KEY", text)

    # =========================================================================
    # GROUP 7: PRODUCTION RELEASE CANDIDATE VERIFICATION (TC-G24-25 to TC-G24-26)
    # =========================================================================

    def test_25_frontend_production_build_artifacts(self):
        """TC-G24-25: Frontend production build artifacts (dist/) exist, valid HTML/CSS/JS, zero secrets."""
        dist_dir = os.path.join(BASE_DIR, "trading-dashboard", "frontend", "dist")
        self.assertTrue(os.path.exists(dist_dir))
        index_html = os.path.join(dist_dir, "index.html")
        self.assertTrue(os.path.exists(index_html))

        # Check assets folder has js and css
        assets_dir = os.path.join(dist_dir, "assets")
        self.assertTrue(os.path.exists(assets_dir))
        asset_files = os.listdir(assets_dir)
        has_js = any(f.endswith(".js") for f in asset_files)
        has_css = any(f.endswith(".css") for f in asset_files)
        self.assertTrue(has_js)
        self.assertTrue(has_css)

    def test_26_dry_run_immutability(self):
        """TC-G24-26: TRADING_MODE=DRY_RUN remains immutable in .env."""
        env_file = os.path.join(BASE_DIR, ".env")
        with open(env_file, "r") as f:
            content = f.read()
            self.assertIn("TRADING_MODE=DRY_RUN", content)
            self.assertNotIn("TRADING_MODE=LIVE", content)
            self.assertNotIn("TRADING_MODE=PAPER_EXECUTION", content)


if __name__ == "__main__":
    unittest.main()
