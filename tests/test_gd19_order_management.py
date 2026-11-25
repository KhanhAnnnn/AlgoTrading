"""
tests/test_gd19_order_management.py — GĐ19 Order Management & Mock Broker Test Suite
Verifies:
1. Mock Broker engine (account, positions, orders, validation, replace, cancel, activities)
2. All Order Types: Market, Limit, Stop, Stop-Limit, Trailing Stop, Fractional, Notional
3. Idempotency & duplicate client_order_id protection
4. Strict isolation: Mock orders never mutate broker or mix with real Alpaca orders
5. Server-side execution safety guards (403 Forbidden on live trade endpoints)
6. Backend REST API coverage for /api/workbench/* endpoints
7. Non-regression of existing /api/paper/* and /api/health endpoints
8. Soak session preservation: Flink and Docker containers remain running undisturbed
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

from mock_trading_broker import MockTradingBroker

API_BASE = "http://127.0.0.1:8005"
TEST_STATE_FILE = os.path.join(BASE_DIR, "data", "mock_broker", "unit_test_mock_state.json")


class TestGD19OrderManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated mock broker for testing
        cls.broker = MockTradingBroker(TEST_STATE_FILE)
        cls.broker.reset_account(100000.0)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_STATE_FILE):
            try:
                os.remove(TEST_STATE_FILE)
            except Exception:
                pass

    # ==========================================================================
    # GROUP 1: MOCK BROKER CORE ENGINE & ACCOUNT DYNAMICS
    # ==========================================================================
    def test_01_account_overview_baseline(self):
        """TC-G19-01: Verify pristine simulated account initialization."""
        acc = self.broker.get_account()
        self.assertEqual(acc["status"], "ACTIVE")
        self.assertEqual(acc["currency"], "USD")
        self.assertEqual(acc["cash"], 100000.0)
        self.assertEqual(acc["equity"], 100000.0)
        self.assertEqual(acc["buying_power"], 400000.0)
        self.assertTrue(acc["is_mock"])
        self.assertEqual(acc["broker"], "SIMULATED_MOCK_BROKER")

    def test_02_market_order_buy_and_fill(self):
        """TC-G19-02: Market BUY order fills immediately, creating position and deducting cash."""
        order = self.broker.submit_order({
            "symbol": "NVDA",
            "side": "buy",
            "type": "market",
            "qty": 10.0
        }, auto_fill=True)

        self.assertEqual(order["status"], "filled")
        self.assertEqual(order["symbol"], "NVDA")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["filled_qty"], 10.0)
        self.assertIsNotNone(order["filled_avg_price"])
        self.assertGreater(order["filled_avg_price"], 0)

        # Check position
        positions = self.broker.get_positions()
        pos = next((p for p in positions if p["symbol"] == "NVDA"), None)
        self.assertIsNotNone(pos)
        self.assertEqual(pos["qty"], 10.0)
        self.assertEqual(pos["avg_entry_price"], order["filled_avg_price"])

        # Check cash deducted
        acc = self.broker.get_account()
        expected_cost = 10.0 * order["filled_avg_price"]
        self.assertAlmostEqual(acc["cash"], 100000.0 - expected_cost, places=2)
        self.assertAlmostEqual(acc["equity"], 100000.0, places=2)

    def test_03_market_order_sell_realizes_pl(self):
        """TC-G19-03: Market SELL order reduces position and returns cash."""
        order_sell = self.broker.submit_order({
            "symbol": "NVDA",
            "side": "sell",
            "type": "market",
            "qty": 5.0
        }, auto_fill=True)

        self.assertEqual(order_sell["status"], "filled")
        self.assertEqual(order_sell["filled_qty"], 5.0)

        positions = self.broker.get_positions()
        pos = next((p for p in positions if p["symbol"] == "NVDA"), None)
        self.assertIsNotNone(pos)
        self.assertEqual(pos["qty"], 5.0)

    # ==========================================================================
    # GROUP 2: ORDER TYPE VALIDATION RULES
    # ==========================================================================
    def test_04_limit_order_validation(self):
        """TC-G19-04: Limit orders require positive limit_price."""
        # Missing limit_price
        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 5})

        # Negative limit_price
        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 5, "limit_price": -10.0})

        # Valid limit order
        o = self.broker.submit_order({"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 5, "limit_price": 220.0})
        self.assertEqual(o["status"], "new")
        self.assertEqual(o["limit_price"], 220.0)

    def test_05_stop_order_validation(self):
        """TC-G19-05: Stop orders require positive stop_price."""
        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "TSLA", "side": "sell", "type": "stop", "qty": 2})

        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "TSLA", "side": "sell", "type": "stop", "qty": 2, "stop_price": 0})

        o = self.broker.submit_order({"symbol": "TSLA", "side": "sell", "type": "stop", "qty": 2, "stop_price": 200.0})
        self.assertEqual(o["status"], "new")
        self.assertEqual(o["stop_price"], 200.0)

    def test_06_stop_limit_order_validation(self):
        """TC-G19-06: Stop Limit orders require both limit_price and stop_price."""
        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "AAPL", "side": "sell", "type": "stop_limit", "qty": 1, "limit_price": 210.0})

        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "AAPL", "side": "sell", "type": "stop_limit", "qty": 1, "stop_price": 215.0})

        o = self.broker.submit_order({
            "symbol": "AAPL",
            "side": "sell",
            "type": "stop_limit",
            "qty": 1,
            "limit_price": 210.0,
            "stop_price": 215.0
        })
        self.assertEqual(o["status"], "new")
        self.assertEqual(o["limit_price"], 210.0)
        self.assertEqual(o["stop_price"], 215.0)

    def test_07_trailing_stop_validation(self):
        """TC-G19-07: Trailing Stop requires trail_price or trail_percent (mutually exclusive)."""
        with self.assertRaises(ValueError):
            self.broker.submit_order({"symbol": "NVDA", "side": "sell", "type": "trailing_stop", "qty": 1})

        with self.assertRaises(ValueError):
            self.broker.submit_order({
                "symbol": "NVDA", "side": "sell", "type": "trailing_stop", "qty": 1,
                "trail_price": 5.0, "trail_percent": 3.0
            })

        o_trail_pct = self.broker.submit_order({
            "symbol": "NVDA", "side": "sell", "type": "trailing_stop", "qty": 1, "trail_percent": 2.5
        })
        self.assertEqual(o_trail_pct["status"], "new")
        self.assertEqual(o_trail_pct["trail_percent"], 2.5)

    def test_08_fractional_and_notional_orders(self):
        """TC-G19-08: Support fractional quantities and notional orders ($ value)."""
        # Fractional crypto order
        o_frac = self.broker.submit_order({
            "symbol": "BTC/USD", "side": "buy", "type": "market", "qty": 0.0025
        })
        self.assertEqual(o_frac["filled_qty"], 0.0025)

        # Notional USD order
        o_notional = self.broker.submit_order({
            "symbol": "ETH/USD", "side": "buy", "type": "market", "notional": 500.0
        })
        self.assertEqual(o_notional["status"], "filled")
        self.assertAlmostEqual(o_notional["filled_qty"] * o_notional["filled_avg_price"], 500.0, delta=1.0)

    def test_09_mutually_exclusive_qty_notional(self):
        """TC-G19-09: Rejects orders with both qty and notional specified."""
        with self.assertRaises(ValueError):
            self.broker.submit_order({
                "symbol": "AAPL", "side": "buy", "type": "market", "qty": 5, "notional": 1000.0
            })

    # ==========================================================================
    # GROUP 3: IDEMPOTENCY, REPLACE & CANCEL
    # ==========================================================================
    def test_10_client_order_id_idempotency(self):
        """TC-G19-10: Duplicate client_order_id is rejected with idempotency violation."""
        cid = "test_cli_idempotent_123"
        o1 = self.broker.submit_order({
            "symbol": "NVDA", "side": "buy", "type": "limit", "qty": 1, "limit_price": 130.0,
            "client_order_id": cid
        })
        self.assertEqual(o1["client_order_id"], cid)

        with self.assertRaises(ValueError) as ctx:
            self.broker.submit_order({
                "symbol": "NVDA", "side": "buy", "type": "limit", "qty": 1, "limit_price": 130.0,
                "client_order_id": cid
            })
        self.assertIn("Duplicate client_order_id", str(ctx.exception))

    def test_11_order_replacement_lifecycle(self):
        """TC-G19-11: Replace order marks old as replaced and spawns linked replacement."""
        old_order = self.broker.submit_order({
            "symbol": "AAPL", "side": "buy", "type": "limit", "qty": 10, "limit_price": 215.0
        })
        new_order = self.broker.replace_order(old_order["id"], {"qty": 15, "limit_price": 218.0})

        self.assertEqual(new_order["replaces"], old_order["id"])
        self.assertEqual(new_order["qty"], 15.0)
        self.assertEqual(new_order["limit_price"], 218.0)
        self.assertEqual(new_order["status"], "new")

        # Verify old order state
        old_refetched = self.broker.get_order_by_id(old_order["id"])
        self.assertEqual(old_refetched["status"], "replaced")
        self.assertEqual(old_refetched["replaced_by"], new_order["id"])

    def test_12_order_cancellation_and_bulk_cancel(self):
        """TC-G19-12: Single cancel and bulk cancel operations."""
        o = self.broker.submit_order({
            "symbol": "TSLA", "side": "buy", "type": "limit", "qty": 4, "limit_price": 210.0
        })
        canceled = self.broker.cancel_order(o["id"])
        self.assertEqual(canceled["status"], "canceled")
        self.assertIsNotNone(canceled["canceled_at"])

        # Bulk cancel
        self.broker.submit_order({"symbol": "TSLA", "side": "buy", "type": "limit", "qty": 1, "limit_price": 205.0})
        self.broker.submit_order({"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 1, "limit_price": 200.0})
        bulk_canceled = self.broker.cancel_all_orders()
        self.assertGreaterEqual(len(bulk_canceled), 2)

    def test_13_order_activity_audit_trail(self):
        """TC-G19-13: Comprehensive audit activities logged for every order event."""
        acts = self.broker.get_activities(limit=50)
        self.assertGreater(len(acts), 0)
        types = [a["activity_type"] for a in acts]
        self.assertIn("CREATED", types)
        self.assertIn("FILLED", types)

    # ==========================================================================
    # GROUP 4: SAFETY, ISOLATION & LIVE BROKER IMMUNITY
    # ==========================================================================
    def test_14_mock_broker_strict_tagging(self):
        """TC-G19-14: Every mock order and account is explicitly tagged and isolated."""
        acc = self.broker.get_account()
        self.assertTrue(acc["is_mock"])
        self.assertEqual(acc["broker"], "SIMULATED_MOCK_BROKER")

        orders = self.broker.get_orders(limit=10)
        for o in orders:
            self.assertTrue(o["is_mock"])
            self.assertEqual(o["broker"], "SIMULATED_MOCK_BROKER")
            self.assertTrue(o["id"].startswith("mock_ord_"))

    def test_15_server_side_safety_guards_assert_403(self):
        """TC-G19-15: Server-side safety guards reject any real order submissions with HTTP 403."""
        endpoints = ["/api/orders", "/api/trade", "/api/v2/orders"]
        for ep in endpoints:
            r = requests.post(f"{API_BASE}{ep}", json={"symbol": "NVDA", "qty": 1, "side": "buy"}, timeout=5)
            self.assertEqual(r.status_code, 403, f"Endpoint {ep} must be blocked with 403 Forbidden")
            self.assertIn("SAFETY GUARD", r.json().get("detail", ""))

    # ==========================================================================
    # GROUP 5: BACKEND REST API COVERAGE (/api/workbench/*)
    # ==========================================================================
    def test_16_backend_workbench_account_api(self):
        """TC-G19-16: GET /api/workbench/account returns simulated account overview."""
        r = requests.get(f"{API_BASE}/api/workbench/account", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("is_mock"))
        self.assertIn("cash", data)
        self.assertIn("equity", data)
        self.assertIn("buying_power", data)

    def test_17_backend_workbench_positions_api(self):
        """TC-G19-17: GET /api/workbench/positions returns open simulation positions."""
        r = requests.get(f"{API_BASE}/api/workbench/positions", timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_18_backend_workbench_orders_and_filtering_api(self):
        """TC-G19-18: GET /api/workbench/orders supports filtering by status, symbol, side."""
        # Query all
        r_all = requests.get(f"{API_BASE}/api/workbench/orders", timeout=5)
        self.assertEqual(r_all.status_code, 200)
        self.assertIsInstance(r_all.json(), list)

        # Query filtered
        r_open = requests.get(f"{API_BASE}/api/workbench/orders?status=open", timeout=5)
        self.assertEqual(r_open.status_code, 200)

        r_sym = requests.get(f"{API_BASE}/api/workbench/orders?symbol=NVDA", timeout=5)
        self.assertEqual(r_sym.status_code, 200)

    def test_19_backend_workbench_order_submission_api(self):
        """TC-G19-19: POST /api/workbench/orders creates simulated order."""
        payload = {"symbol": "NVDA", "side": "buy", "type": "market", "qty": 2}
        r = requests.post(f"{API_BASE}/api/workbench/orders", json=payload, timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "filled")
        self.assertEqual(data["symbol"], "NVDA")
        self.assertTrue(data["is_mock"])

    def test_20_backend_workbench_order_details_and_activities_api(self):
        """TC-G19-20: GET /api/workbench/orders/{id} returns details and lifecycle activities."""
        # Create an order
        r_create = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "AAPL", "side": "buy", "type": "limit", "qty": 3, "limit_price": 225.0
        }, timeout=5)
        self.assertEqual(r_create.status_code, 200)
        oid = r_create.json()["id"]

        r_det = requests.get(f"{API_BASE}/api/workbench/orders/{oid}", timeout=5)
        self.assertEqual(r_det.status_code, 200)
        det_data = r_det.json()
        self.assertIn("order", det_data)
        self.assertIn("activities", det_data)
        self.assertEqual(det_data["order"]["id"], oid)

    def test_21_backend_workbench_replace_and_cancel_api(self):
        """TC-G19-21: PATCH and DELETE /api/workbench/orders/{id} operations."""
        r_create = requests.post(f"{API_BASE}/api/workbench/orders", json={
            "symbol": "TSLA", "side": "buy", "type": "limit", "qty": 5, "limit_price": 200.0
        }, timeout=5)
        oid = r_create.json()["id"]

        # Replace
        r_rep = requests.patch(f"{API_BASE}/api/workbench/orders/{oid}", json={
            "qty": 8, "limit_price": 202.0
        }, timeout=5)
        self.assertEqual(r_rep.status_code, 200)
        new_oid = r_rep.json()["id"]

        # Cancel
        r_can = requests.delete(f"{API_BASE}/api/workbench/orders/{new_oid}", timeout=5)
        self.assertEqual(r_can.status_code, 200)
        self.assertEqual(r_can.json()["status"], "canceled")

    def test_22_backend_workbench_activities_api(self):
        """TC-G19-22: GET /api/workbench/activities returns full audit log."""
        r = requests.get(f"{API_BASE}/api/workbench/activities?limit=20", timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_23_backend_workbench_reset_api(self):
        """TC-G19-23: POST /api/workbench/reset restores baseline simulation state."""
        r = requests.post(f"{API_BASE}/api/workbench/reset", timeout=5)
        self.assertEqual(r.status_code, 200)
        acc = r.json()
        self.assertEqual(acc["cash"], 100000.0)

    # ==========================================================================
    # GROUP 6: REGRESSION TESTING & SOAK SESSION PRESERVATION
    # ==========================================================================
    def test_24_alpaca_paper_read_endpoints_uncompromised(self):
        """TC-G19-24: Read-only Alpaca Paper endpoints continue serving real broker telemetry."""
        r_acc = requests.get(f"{API_BASE}/api/paper/account", timeout=5)
        self.assertEqual(r_acc.status_code, 200)

        r_pos = requests.get(f"{API_BASE}/api/paper/positions", timeout=5)
        self.assertEqual(r_pos.status_code, 200)

        r_ord = requests.get(f"{API_BASE}/api/paper/orders", timeout=5)
        self.assertEqual(r_ord.status_code, 200)

    def test_25_dashboard_health_and_system_status_regression(self):
        """TC-G19-25: Core health and system status endpoints remain 200 OK."""
        r_health = requests.get(f"{API_BASE}/api/health", timeout=5)
        self.assertEqual(r_health.status_code, 200)

        r_sys = requests.get(f"{API_BASE}/api/system/status", timeout=5)
        self.assertEqual(r_sys.status_code, 200)
        st = r_sys.json()
        self.assertIn("pipeline_verdict", st)

    def test_26_soak_runtime_preservation(self):
        """TC-G19-26: Production Flink streaming jobs remain RUNNING 6/6 tasks undisturbed."""
        r_flink = requests.get("http://localhost:8081/jobs/overview", timeout=5)
        self.assertEqual(r_flink.status_code, 200)
        jobs = r_flink.json().get("jobs", [])
        running = [j for j in jobs if j.get("state") == "RUNNING" and j.get("tasks", {}).get("running") == 6]
        self.assertGreaterEqual(len(running), 2, "Both Stocks and Crypto Flink streaming jobs must remain RUNNING 6/6 tasks")


if __name__ == "__main__":
    unittest.main()

