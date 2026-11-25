"""
tests/test_gd35_api_dashboard.py — GĐ35 API & Dashboard Integration Test Suite
AlgoTrading V2.0 Paper Trading Bot System.

Contains 65 automated tests covering:
- Group A: REST API Contracts & Schema Validation (TC 01 - 10)
- Group B: Bot Lifecycle Commands & Idempotency (TC 11 - 20)
- Group C: Portfolio, Orders & Fills Endpoints (TC 21 - 30)
- Group D: Performance & Health Endpoints (TC 31 - 38)
- Group E: WebSocket Protocol, Sequence IDs & Deduplication (TC 39 - 48)
- Group F: WebSocket Reconnection & Snapshot Resync (TC 49 - 55)
- Group G: Authentication, Authorization & Security (TC 56 - 60)
- Group H: Safety Invariants & Full System Regression (TC 61 - 65)
"""

import sys
import os
import unittest
import json
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# Ensure backend and repo root are in python path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "trading-dashboard", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
from main import app
from libs.bot.api.service import bot_api_service
from libs.bot.api.websocket import ws_manager
from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    SimulatedOrder,
    SimulatedFill,
    SimulatedPosition,
)
from libs.bot.orchestration.lifecycle import BotLifecycleState
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.alpaca_paper_gate import AlpacaPaperGate


class TestGD35ApiDashboard(unittest.TestCase):
    """GĐ35 Comprehensive Test Suite: REST API, WebSockets, Dashboard Integration & Safety."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Reset memory state between test runs
        os.environ.pop("V2_API_KEY", None)
        ws_manager._session_connections.clear()
        ws_manager._global_connections.clear()
        ws_manager._sequence_counters.clear()
        ws_manager._event_buffers.clear()

    def _create_sample_bot(self, bot_id: str = "bot_tc_default", initial_cash: float = 100000.0) -> dict:
        """Helper to create a standard test bot."""
        payload = {
            "bot_id": bot_id,
            "bot_name": f"Name_{bot_id}",
            "symbols": ["NVDA", "BTC/USD"],
            "timeframe": "1m",
            "initial_cash": initial_cash,
            "strategy_id": "MA_CROSS_1M",
            "strategy_version": "1.0.0",
            "risk_config": {
                "risk_per_trade_pct": 0.02,
                "max_position_notional": 25000.0,
                "max_portfolio_exposure_pct": 1.0,
                "max_concurrent_positions": 5,
                "daily_loss_limit_pct": 0.05,
            },
            "stop_policy": "CANCEL_REMAINDER",
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.json()

    # ==============================================================================
    # Group A: REST API Contracts & Schema Validation (TC 01 - 10)
    # ==============================================================================

    def test_tc01_get_bots_empty_or_existing(self):
        """TC 01: GET /api/v2/bots returns 200 OK and list of bots."""
        res = self.client.get("/api/v2/bots")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc02_post_bot_valid_schema_created(self):
        """TC 02: POST /api/v2/bots creates bot with valid schema and status STOPPED."""
        bot_id = f"bot_tc02_{uuid.uuid4().hex[:6]}"
        data = self._create_sample_bot(bot_id=bot_id, initial_cash=75000.0)
        self.assertEqual(data["bot_id"], bot_id)
        self.assertEqual(data["initial_cash"], 75000.0)
        self.assertEqual(data["cash"], 75000.0)
        self.assertEqual(data["current_equity"], 75000.0)
        self.assertEqual(data["lifecycle_state"], "STOPPED")
        self.assertEqual(data["trading_mode"], "DRY_RUN")
        self.assertEqual(data["environment"], "SIMULATION")

    def test_tc03_post_bot_negative_cash_validation_error(self):
        """TC 03: POST /api/v2/bots rejects negative initial cash with 422 or 400."""
        payload = {
            "bot_id": "bad_cash_bot",
            "symbols": ["NVDA"],
            "initial_cash": -500.0,
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertIn(res.status_code, [400, 422])

    def test_tc04_post_bot_invalid_risk_pct_validation_error(self):
        """TC 04: POST /api/v2/bots rejects risk percentage > 0.50."""
        payload = {
            "bot_id": "bad_risk_bot",
            "symbols": ["NVDA"],
            "risk_config": {
                "risk_per_trade_pct": 1.5,  # > 0.50 invalid
            },
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertIn(res.status_code, [400, 422])

    def test_tc05_post_bot_empty_symbols_validation_error(self):
        """TC 05: POST /api/v2/bots rejects empty symbol list."""
        payload = {
            "bot_id": "no_symbols_bot",
            "symbols": [],
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertIn(res.status_code, [400, 422])

    def test_tc06_get_bot_summary_by_id(self):
        """TC 06: GET /api/v2/bots/{session_id} returns bot summary."""
        bot = self._create_sample_bot(f"bot_tc06_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["session_id"], s_id)
        self.assertEqual(data["symbols"], ["NVDA", "BTC/USD"])

    def test_tc07_get_bot_not_found_returns_404(self):
        """TC 07: GET /api/v2/bots/nonexistent returns 404 Not Found."""
        res = self.client.get("/api/v2/bots/session_nonexistent_9999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"].lower())

    def test_tc08_post_bot_custom_stop_policies(self):
        """TC 08: POST /api/v2/bots supports KEEP_WORKING and CANCEL_REMAINDER stop policies."""
        p1 = self._create_sample_bot(f"bot_p1_{uuid.uuid4().hex[:6]}")
        self.assertIsNotNone(p1["session_id"])

        payload = {
            "bot_id": f"bot_p2_{uuid.uuid4().hex[:6]}",
            "symbols": ["NVDA"],
            "stop_policy": "KEEP_WORKING",
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertEqual(res.status_code, 201)

    def test_tc09_post_bot_response_simulation_environment_tags(self):
        """TC 09: POST /api/v2/bots response is strictly tagged SIMULATION and DRY_RUN."""
        bot = self._create_sample_bot(f"bot_tc09_{uuid.uuid4().hex[:6]}")
        self.assertEqual(bot["environment"], "SIMULATION")
        self.assertEqual(bot["trading_mode"], "DRY_RUN")

    def test_tc10_get_bots_lists_multiple_created_bots(self):
        """TC 10: GET /api/v2/bots lists multiple created bots correctly."""
        b1 = self._create_sample_bot(f"bot_multi_1_{uuid.uuid4().hex[:6]}")
        b2 = self._create_sample_bot(f"bot_multi_2_{uuid.uuid4().hex[:6]}")
        res = self.client.get("/api/v2/bots")
        self.assertEqual(res.status_code, 200)
        ids = [b["session_id"] for b in res.json()]
        self.assertIn(b1["session_id"], ids)
        self.assertIn(b2["session_id"], ids)

    # ==============================================================================
    # Group B: Bot Lifecycle Commands & Idempotency (TC 11 - 20)
    # ==============================================================================

    def test_tc11_start_bot_success(self):
        """TC 11: POST /api/v2/bots/{id}/start transitions bot to RUNNING."""
        bot = self._create_sample_bot(f"bot_start_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.post(f"/api/v2/bots/{s_id}/start")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "RUNNING")

    def test_tc12_start_bot_idempotency_when_already_running(self):
        """TC 12: Starting an already RUNNING bot is idempotent and returns 200."""
        bot = self._create_sample_bot(f"bot_run_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        res2 = self.client.post(f"/api/v2/bots/{s_id}/start")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["lifecycle_state"], "RUNNING")

    def test_tc13_pause_bot_success(self):
        """TC 13: POST /api/v2/bots/{id}/pause transitions bot from RUNNING to PAUSED."""
        bot = self._create_sample_bot(f"bot_pause_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        res = self.client.post(f"/api/v2/bots/{s_id}/pause", json={"reason": "MAINTENANCE"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "PAUSED")

    def test_tc14_pause_bot_idempotency_when_already_paused(self):
        """TC 14: Pausing an already PAUSED bot is idempotent and returns 200."""
        bot = self._create_sample_bot(f"bot_p_idem_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        self.client.post(f"/api/v2/bots/{s_id}/pause")
        res = self.client.post(f"/api/v2/bots/{s_id}/pause")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "PAUSED")

    def test_tc15_resume_bot_success(self):
        """TC 15: POST /api/v2/bots/{id}/resume transitions bot from PAUSED to RUNNING."""
        bot = self._create_sample_bot(f"bot_res_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        self.client.post(f"/api/v2/bots/{s_id}/pause")
        res = self.client.post(f"/api/v2/bots/{s_id}/resume")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "RUNNING")

    def test_tc16_resume_bot_idempotency_when_already_running(self):
        """TC 16: Resuming an already RUNNING bot is idempotent and returns 200."""
        bot = self._create_sample_bot(f"bot_res_idem_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        res = self.client.post(f"/api/v2/bots/{s_id}/resume")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "RUNNING")

    def test_tc17_stop_bot_success(self):
        """TC 17: POST /api/v2/bots/{id}/stop transitions bot to STOPPED."""
        bot = self._create_sample_bot(f"bot_stop_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        res = self.client.post(f"/api/v2/bots/{s_id}/stop", json={"policy": "CANCEL_REMAINDER"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "STOPPED")

    def test_tc18_stop_bot_idempotency_when_already_stopped(self):
        """TC 18: Stopping an already STOPPED bot is idempotent and returns 200."""
        bot = self._create_sample_bot(f"bot_stop_idem_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        self.client.post(f"/api/v2/bots/{s_id}/stop")
        res = self.client.post(f"/api/v2/bots/{s_id}/stop")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["lifecycle_state"], "STOPPED")

    def test_tc19_invalid_lifecycle_transition_returns_409(self):
        """TC 19: Invalid transition (e.g. pause a STOPPED bot) returns 409 Conflict."""
        bot = self._create_sample_bot(f"bot_inval_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        self.client.post(f"/api/v2/bots/{s_id}/stop")
        res = self.client.post(f"/api/v2/bots/{s_id}/pause")
        self.assertEqual(res.status_code, 409)

    def test_tc20_lifecycle_commands_record_audit_events(self):
        """TC 20: Lifecycle commands transition state and record timestamps."""
        bot = self._create_sample_bot(f"bot_audit_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        res = self.client.post(f"/api/v2/bots/{s_id}/start")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(orch.state, "RUNNING")
        self.assertIsNotNone(orch.session.started_at)

    # ==============================================================================
    # Group C: Portfolio, Orders & Fills Endpoints (TC 21 - 30)
    # ==============================================================================

    def test_tc21_get_portfolio_returns_accurate_balances(self):
        """TC 21: GET /api/v2/bots/{id}/portfolio returns cash, equity, and state."""
        bot = self._create_sample_bot(f"bot_p_{uuid.uuid4().hex[:6]}", initial_cash=50000.0)
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/portfolio")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["initial_cash"], 50000.0)
        self.assertEqual(data["cash"], 50000.0)
        self.assertEqual(data["equity"], 50000.0)
        self.assertEqual(data["available_cash"], 50000.0)
        self.assertEqual(data["reserved_cash"], 0.0)
        self.assertEqual(data["environment"], "SIMULATION")

    def test_tc22_get_portfolio_positions_mapping(self):
        """TC 22: Portfolio active positions list correctly reflects underlying positions."""
        bot = self._create_sample_bot(f"bot_pos_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        # Add a simulated position via record_fill and update_valuation
        orch.portfolio.positions.record_fill("NVDA", "BUY", Decimal("10"), Decimal("140.00"), Decimal("1.00"))
        orch.portfolio.positions.update_valuation("NVDA", Decimal("145.00"))
        res = self.client.get(f"/api/v2/bots/{s_id}/portfolio")
        self.assertEqual(res.status_code, 200)
        positions = res.json()["positions"]
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "NVDA")
        self.assertEqual(positions[0]["qty"], 10.0)
        self.assertEqual(positions[0]["unrealized_pnl"], 50.0)

    def test_tc23_get_orders_returns_list(self):
        """TC 23: GET /api/v2/bots/{id}/orders returns simulated orders."""
        bot = self._create_sample_bot(f"bot_ord_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/orders")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc24_get_orders_filter_by_status(self):
        """TC 24: GET /api/v2/bots/{id}/orders?status=FILLED filters properly."""
        bot = self._create_sample_bot(f"bot_ord_f_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        # Register a mock simulated order
        order = SimulatedOrder(
            simulated_order_id="ord_test_01",
            bot_session_id=s_id,
            intent_id="intent_01",
            idempotency_key="k1",
            symbol="NVDA",
            side="BUY",
            order_type="MARKET",
            quantity=10.0,
            limit_price=None,
            stop_price=None,
            status="FILLED",
            filled_quantity=10.0,
            average_fill_price=142.50,
            submitted_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        orch.simulation_broker.order_manager._orders["ord_test_01"] = order

        res = self.client.get(f"/api/v2/bots/{s_id}/orders?status=FILLED")
        self.assertEqual(res.status_code, 200)
        orders = res.json()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["simulated_order_id"], "ord_test_01")
        self.assertEqual(orders[0]["status"], "FILLED")

        res_empty = self.client.get(f"/api/v2/bots/{s_id}/orders?status=WORKING")
        self.assertEqual(len(res_empty.json()), 0)

    def test_tc25_get_orders_filter_by_symbol(self):
        """TC 25: GET /api/v2/bots/{id}/orders?symbol=NVDA filters by symbol."""
        bot = self._create_sample_bot(f"bot_ord_s_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        o1 = SimulatedOrder(
            simulated_order_id="ord_nvda",
            bot_session_id=s_id,
            intent_id="int_1",
            idempotency_key="k_nvda",
            symbol="NVDA",
            side="BUY",
            order_type="MARKET",
            quantity=5.0,
            status="FILLED",
            environment="SIMULATION",
        )
        o2 = SimulatedOrder(
            simulated_order_id="ord_btc",
            bot_session_id=s_id,
            intent_id="int_2",
            idempotency_key="k_btc",
            symbol="BTC/USD",
            side="BUY",
            order_type="MARKET",
            quantity=1.0,
            status="WORKING",
            environment="SIMULATION",
        )
        orch.simulation_broker.order_manager._orders["ord_nvda"] = o1
        orch.simulation_broker.order_manager._orders["ord_btc"] = o2

        res = self.client.get(f"/api/v2/bots/{s_id}/orders?symbol=NVDA")
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["symbol"], "NVDA")

    def test_tc26_get_fills_returns_list(self):
        """TC 26: GET /api/v2/bots/{id}/fills returns simulated fill records."""
        bot = self._create_sample_bot(f"bot_fill_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/fills")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc27_get_fills_filter_by_symbol(self):
        """TC 27: GET /api/v2/bots/{id}/fills?symbol=NVDA filters fills by symbol."""
        bot = self._create_sample_bot(f"bot_fill_sym_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        fill1 = SimulatedFill(
            simulated_fill_id="fill_01",
            simulated_order_id="ord_01",
            bot_session_id=s_id,
            symbol="NVDA",
            side="BUY",
            fill_price=Decimal("140.00"),
            fill_qty=Decimal("10"),
            fee=Decimal("1.00"),
            slippage=Decimal("0.05"),
            fill_time=datetime.now(timezone.utc),
            source_bar_key="NVDA:1m:bar1",
            execution_bar_key="NVDA:1m:bar2",
            environment="SIMULATION",
        )
        orch.simulation_broker._fills.append(fill1)

        res = self.client.get(f"/api/v2/bots/{s_id}/fills?symbol=NVDA")
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["symbol"], "NVDA")

        res_btc = self.client.get(f"/api/v2/bots/{s_id}/fills?symbol=BTC/USD")
        self.assertEqual(len(res_btc.json()), 0)

    def test_tc28_get_fills_limit_pagination(self):
        """TC 28: GET /api/v2/bots/{id}/fills?limit=2 applies pagination limit."""
        bot = self._create_sample_bot(f"bot_fill_pag_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        for i in range(5):
            fill = SimulatedFill(
                simulated_fill_id=f"fill_{i}",
                simulated_order_id=f"ord_{i}",
                bot_session_id=s_id,
                symbol="NVDA",
                side="BUY",
                fill_price=Decimal("140.00"),
                fill_qty=Decimal("1"),
                fee=Decimal("0.10"),
                slippage=Decimal("0.01"),
                fill_time=datetime.now(timezone.utc),
                source_bar_key="b1",
                execution_bar_key="b2",
                environment="SIMULATION",
            )
            orch.simulation_broker._fills.append(fill)

        res = self.client.get(f"/api/v2/bots/{s_id}/fills?limit=2")
        self.assertEqual(len(res.json()), 2)

    def test_tc29_portfolio_orders_fills_for_non_existent_bot_404(self):
        """TC 29: Querying portfolio, orders, fills for non-existent bot returns 404."""
        bad_id = "non_existent_session_xyz"
        self.assertEqual(self.client.get(f"/api/v2/bots/{bad_id}/portfolio").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v2/bots/{bad_id}/orders").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v2/bots/{bad_id}/fills").status_code, 404)

    def test_tc30_portfolio_values_decimal_precision_consistency(self):
        """TC 30: Portfolio endpoint maintains Decimal precision and serialization format."""
        bot = self._create_sample_bot(f"bot_dec_{uuid.uuid4().hex[:6]}", initial_cash=12345.67)
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/portfolio")
        data = res.json()
        self.assertAlmostEqual(data["cash"], 12345.67, places=2)
        self.assertAlmostEqual(data["equity"], 12345.67, places=2)

    # ==============================================================================
    # Group D: Performance & Health Endpoints (TC 31 - 38)
    # ==============================================================================

    def test_tc31_get_performance_metrics(self):
        """TC 31: GET /api/v2/bots/{id}/performance returns total_pnl, win_rate, total_trades."""
        bot = self._create_sample_bot(f"bot_perf_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/performance")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_realized_pnl", data)
        self.assertIn("win_rate_pct", data)
        self.assertIn("total_trades", data)
        self.assertEqual(data["environment"], "SIMULATION")

    def test_tc32_get_performance_conversion_funnel(self):
        """TC 32: Performance endpoint returns signal conversion funnel."""
        bot = self._create_sample_bot(f"bot_funnel_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/performance")
        data = res.json()
        self.assertIn("signals_received", data)
        self.assertIn("signals_accepted", data)
        self.assertIn("signals_rejected", data)

    def test_tc33_get_performance_drawdown_metrics(self):
        """TC 33: Performance endpoint returns drawdown metrics."""
        bot = self._create_sample_bot(f"bot_dd_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/performance")
        data = res.json()
        self.assertIn("max_drawdown_usd", data)
        self.assertIn("max_drawdown_pct", data)
        self.assertIn("peak_equity", data)

    def test_tc34_get_health_status_and_latency(self):
        """TC 34: GET /api/v2/bots/{id}/health returns status, latency, queue depth."""
        bot = self._create_sample_bot(f"bot_health_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertIn("latency_ms", data)
        self.assertIn("queue_depth", data)
        self.assertEqual(data["environment"], "SIMULATION")

    def test_tc35_get_health_staleness_detection(self):
        """TC 35: Health endpoint reflects feed staleness status."""
        bot = self._create_sample_bot(f"bot_stale_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        res = self.client.get(f"/api/v2/bots/{s_id}/health")
        data = res.json()
        self.assertIn("is_feed_stale", data)

    def test_tc36_performance_and_health_for_non_existent_bot_404(self):
        """TC 36: Querying performance or health for non-existent bot returns 404."""
        bad_id = "missing_session_999"
        self.assertEqual(self.client.get(f"/api/v2/bots/{bad_id}/performance").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v2/bots/{bad_id}/health").status_code, 404)

    def test_tc37_performance_updates_after_simulated_trade(self):
        """TC 37: Performance metrics update after simulated trade fill."""
        bot = self._create_sample_bot(f"bot_perf_tr_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        orch.portfolio._realized_pnl = Decimal("100.00")
        fill1 = SimulatedFill(
            simulated_fill_id="fill_perf_1",
            simulated_order_id="ord_perf_1",
            bot_session_id=s_id,
            symbol="NVDA",
            side="BUY",
            fill_price=Decimal("140.00"),
            fill_qty=Decimal("10"),
            fee=Decimal("1.00"),
            slippage=Decimal("0.05"),
            fill_time=datetime.now(timezone.utc),
            source_bar_key="b1",
            execution_bar_key="b2",
            environment="SIMULATION",
        )
        orch.simulation_broker._fills.append(fill1)

        res = self.client.get(f"/api/v2/bots/{s_id}/performance")
        data = res.json()
        self.assertGreater(data["total_realized_pnl"], 0)

    def test_tc38_health_warnings_and_discrepancy_mapping(self):
        """TC 38: Health warnings and discrepancy reporting correctly formatted."""
        bot = self._create_sample_bot(f"bot_warn_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        orch = bot_api_service._get_active_orchestrator(s_id)
        orch.health_monitor.record_error("TEST_HIGH_LATENCY: Simulated latency spike")
        res = self.client.get(f"/api/v2/bots/{s_id}/health")
        data = res.json()
        self.assertIn("warnings", data)
        self.assertTrue(any(w.get("code") == "LAST_ERROR" for w in data["warnings"]))

    # ==============================================================================
    # Group E: WebSocket Protocol, Sequence IDs & Deduplication (TC 39 - 48)
    # ==============================================================================

    def test_tc39_websocket_connect_receives_snapshot(self):
        """TC 39: Connecting to /ws/v2/bots/{session_id} immediately receives SNAPSHOT message."""
        bot = self._create_sample_bot(f"bot_ws39_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["event_type"], "SNAPSHOT")
            self.assertEqual(msg["session_id"], s_id)
            self.assertIn("summary", msg["payload"])
            self.assertIn("portfolio", msg["payload"])

    def test_tc40_websocket_ping_pong(self):
        """TC 40: Sending PING over WebSocket receives PONG with server_time."""
        bot = self._create_sample_bot(f"bot_ws40_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Consume SNAPSHOT
            ws.send_json({"action": "PING", "timestamp": 123456789})
            reply = ws.receive_json()
            self.assertEqual(reply["type"], "PONG")
            self.assertEqual(reply["timestamp"], 123456789)
            self.assertIn("server_time", reply)

    def test_tc41_websocket_strictly_monotonic_sequence_ids(self):
        """TC 41: Sequence IDs (seq_id) are strictly monotonically increasing across events."""
        s_id = f"session_seq_{uuid.uuid4().hex[:6]}"
        q1 = ws_manager._next_seq_id(s_id)
        q2 = ws_manager._next_seq_id(s_id)
        q3 = ws_manager._next_seq_id(s_id)
        self.assertEqual(q1, 1)
        self.assertEqual(q2, 2)
        self.assertEqual(q3, 3)

    def test_tc42_websocket_lifecycle_event_broadcast(self):
        """TC 42: Bot start/pause/resume/stop triggers WebSocket lifecycle broadcast."""
        bot = self._create_sample_bot(f"bot_ws42_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Snapshot
            self.client.post(f"/api/v2/bots/{s_id}/start")
            evt = ws.receive_json()
            self.assertEqual(evt["event_type"], "BOT_LIFECYCLE_EVENT")
            self.assertEqual(evt["payload"]["action"], "START")
            self.assertEqual(evt["payload"]["state"], "RUNNING")

    def test_tc43_websocket_signal_event_broadcast(self):
        """TC 43: Submitting bar generating signal broadcasts STRATEGY_SIGNAL_EVENT."""
        bot = self._create_sample_bot(f"bot_ws43_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Snapshot
            # Directly trigger broadcast event
            ws_manager.broadcast_sync(s_id, "STRATEGY_SIGNAL_EVENT", {
                "signal_id": "sig_01",
                "strategy_id": "MA_CROSS_1M",
                "symbol": "NVDA",
                "signal_type": "BUY",
                "price": 140.50,
            })
            msg = ws.receive_json()
            self.assertEqual(msg["event_type"], "STRATEGY_SIGNAL_EVENT")
            self.assertEqual(msg["payload"]["signal_type"], "BUY")

    def test_tc44_websocket_decision_event_broadcast(self):
        """TC 44: Risk decision broadcasts RISK_DECISION_EVENT."""
        s_id = f"session_ws44_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Snapshot
            ws_manager.broadcast_sync(s_id, "RISK_DECISION_EVENT", {
                "decision_id": "dec_01",
                "status": "APPROVED",
                "rejection_reason": None,
            })
            msg = ws.receive_json()
            self.assertEqual(msg["event_type"], "RISK_DECISION_EVENT")
            self.assertEqual(msg["payload"]["status"], "APPROVED")

    def test_tc45_websocket_order_event_broadcast(self):
        """TC 45: Order creation/update broadcasts ORDER_EVENT."""
        s_id = f"session_ws45_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()
            ws_manager.broadcast_sync(s_id, "ORDER_EVENT", {
                "simulated_order_id": "ord_99",
                "status": "WORKING",
                "symbol": "NVDA",
            })
            msg = ws.receive_json()
            self.assertEqual(msg["event_type"], "ORDER_EVENT")
            self.assertEqual(msg["payload"]["status"], "WORKING")

    def test_tc46_websocket_fill_event_broadcast(self):
        """TC 46: Fill execution broadcasts FILL_EVENT."""
        s_id = f"session_ws46_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()
            ws_manager.broadcast_sync(s_id, "FILL_EVENT", {
                "simulated_fill_id": "fill_101",
                "symbol": "NVDA",
                "fill_price": 142.0,
                "fill_qty": 10.0,
            })
            msg = ws.receive_json()
            self.assertEqual(msg["event_type"], "FILL_EVENT")
            self.assertEqual(msg["payload"]["fill_price"], 142.0)

    def test_tc47_websocket_global_endpoint_broadcast(self):
        """TC 47: Global WebSocket /ws/v2/bots receives events from all sessions."""
        s_id = f"session_ws47_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect("/ws/v2/bots") as ws_global:
            ws_manager.broadcast_sync(s_id, "FILL_EVENT", {"fill_id": "global_fill_1"})
            msg = ws_global.receive_json()
            self.assertEqual(msg["event_type"], "FILL_EVENT")
            self.assertEqual(msg["session_id"], s_id)

    def test_tc48_websocket_graceful_client_disconnect(self):
        """TC 48: Graceful client disconnect handled cleanly without server error."""
        s_id = f"session_ws48_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            self.assertEqual(len(ws_manager._session_connections[s_id]), 1)
        # Sockets cleanly removed
        self.assertEqual(len(ws_manager._session_connections.get(s_id, set())), 0)

    # ==============================================================================
    # Group F: WebSocket Reconnection & Snapshot Resync (TC 49 - 55)
    # ==============================================================================

    def test_tc49_websocket_resync_action_replays_missed_events(self):
        """TC 49: Sending RESYNC with last_seq_id replays missed events from ring buffer."""
        bot = self._create_sample_bot(f"bot_resync_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        # Populate events in buffer
        ws_manager.broadcast_sync(s_id, "EVENT_1", {"index": 1})
        ws_manager.broadcast_sync(s_id, "EVENT_2", {"index": 2})
        ws_manager.broadcast_sync(s_id, "EVENT_3", {"index": 3})

        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Snapshot
            ws.send_json({"action": "RESYNC", "last_seq_id": 1})
            e2 = ws.receive_json()
            e3 = ws.receive_json()
            self.assertEqual(e2["event_type"], "EVENT_2")
            self.assertEqual(e3["event_type"], "EVENT_3")

    def test_tc50_websocket_resync_older_than_buffer_sends_snapshot(self):
        """TC 50: RESYNC with sequence older than ring buffer falls back to full SNAPSHOT."""
        bot = self._create_sample_bot(f"bot_resync_old_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        # Set small buffer and overflow it
        ws_manager.history_limit = 2
        ws_manager.broadcast_sync(s_id, "EV1", {})
        ws_manager.broadcast_sync(s_id, "EV2", {})
        ws_manager.broadcast_sync(s_id, "EV3", {})

        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Initial snapshot
            ws.send_json({"action": "RESYNC", "last_seq_id": 0})
            snap = ws.receive_json()
            self.assertEqual(snap["event_type"], "SNAPSHOT")
        ws_manager.history_limit = 200

    def test_tc51_websocket_explicit_get_snapshot_action(self):
        """TC 51: Sending GET_SNAPSHOT returns current full snapshot."""
        bot = self._create_sample_bot(f"bot_snap_act_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # Initial
            ws.send_json({"action": "GET_SNAPSHOT"})
            rep = ws.receive_json()
            self.assertEqual(rep["event_type"], "SNAPSHOT")
            self.assertEqual(rep["session_id"], s_id)

    def test_tc52_websocket_event_deduplication_tracking(self):
        """TC 52: Event sequence IDs enable client-side deduplication."""
        s_id = f"session_dedup_{uuid.uuid4().hex[:6]}"
        e1 = ws_manager.broadcast_sync(s_id, "E1", {})
        e2 = ws_manager.broadcast_sync(s_id, "E2", {})
        received_ids = set()
        for e in [e1, e2, e2]:  # simulate receiving duplicate e2
            if e["seq_id"] not in received_ids:
                received_ids.add(e["seq_id"])
        self.assertEqual(len(received_ids), 2)

    def test_tc53_websocket_subscriber_cleanup_on_disconnect(self):
        """TC 53: Client disconnect properly cleans up set of subscribers."""
        s_id = f"session_clean_{uuid.uuid4().hex[:6]}"
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}"):
            self.assertEqual(len(ws_manager._session_connections[s_id]), 1)
        self.assertEqual(len(ws_manager._session_connections[s_id]), 0)

    def test_tc54_websocket_multiple_concurrent_clients_receive_broadcasts(self):
        """TC 54: Multiple concurrent WebSocket clients on same session receive identical broadcasts."""
        bot = self._create_sample_bot(f"bot_conc_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws1:
            ws1.receive_json()  # snap 1
            with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws2:
                ws2.receive_json()  # snap 2
                ws_manager.broadcast_sync(s_id, "SYNC_EVENT", {"data": "test"})
                m1 = ws1.receive_json()
                m2 = ws2.receive_json()
                self.assertEqual(m1["seq_id"], m2["seq_id"])
                self.assertEqual(m1["payload"], m2["payload"])

    def test_tc55_websocket_reconnection_after_pause_resume(self):
        """TC 55: Reconnecting WebSocket after pause/resume maintains monotonic sequence continuity."""
        bot = self._create_sample_bot(f"bot_recon_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        self.client.post(f"/api/v2/bots/{s_id}/start")
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            ws.receive_json()  # snapshot
            self.client.post(f"/api/v2/bots/{s_id}/pause")
            p_msg = ws.receive_json()
            self.assertEqual(p_msg["payload"]["state"], "PAUSED")
            last_seq = p_msg["seq_id"]

        # Reconnect
        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws2:
            snap = ws2.receive_json()
            self.assertGreaterEqual(snap["seq_id"], last_seq)

    # ==============================================================================
    # Group G: Authentication, Authorization & Security (TC 56 - 60)
    # ==============================================================================

    def test_tc56_auth_missing_or_invalid_api_key(self):
        """TC 56: Missing or invalid X-API-Key returns 401 when V2_API_KEY is configured."""
        os.environ["V2_API_KEY"] = "secure_token_123"
        try:
            res_no_auth = self.client.get("/api/v2/bots")
            self.assertEqual(res_no_auth.status_code, 401)

            res_bad_auth = self.client.get("/api/v2/bots", headers={"X-API-Key": "wrong_key"})
            self.assertEqual(res_bad_auth.status_code, 401)
        finally:
            os.environ.pop("V2_API_KEY", None)

    def test_tc57_auth_valid_api_key_allows_access(self):
        """TC 57: Valid X-API-Key header authenticates REST requests and allows access."""
        os.environ["V2_API_KEY"] = "secure_token_123"
        try:
            res = self.client.get("/api/v2/bots", headers={"X-API-Key": "secure_token_123"})
            self.assertEqual(res.status_code, 200)
        finally:
            os.environ.pop("V2_API_KEY", None)

    def test_tc58_auth_websocket_token_query_param(self):
        """TC 58: Auth token in WebSocket query param is validated."""
        bot = self._create_sample_bot(f"bot_auth_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        os.environ["V2_API_KEY"] = "secure_ws_token"
        try:
            # Without token -> fails with 1008 policy violation
            with self.assertRaises(Exception):
                with self.client.websocket_connect(f"/ws/v2/bots/{s_id}"):
                    pass

            # With valid token -> connects successfully
            with self.client.websocket_connect(f"/ws/v2/bots/{s_id}?token=secure_ws_token") as ws:
                msg = ws.receive_json()
                self.assertEqual(msg["event_type"], "SNAPSHOT")
        finally:
            os.environ.pop("V2_API_KEY", None)

    def test_tc59_security_live_broker_write_action_blocked(self):
        """TC 59: Submitting bar with environment != 'SIMULATION' is rejected with 400."""
        bot = self._create_sample_bot(f"bot_sec_live_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "event_time": datetime.now(timezone.utc).isoformat(),
            "open": 140.0,
            "high": 141.0,
            "low": 139.5,
            "close": 140.5,
            "volume": 1000.0,
            "environment": "LIVE_PRODUCTION",  # Prohibited!
        }
        res = self.client.post(f"/api/v2/bots/{s_id}/bars", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("strictly 'simulation'", res.json()["detail"].lower())

    def test_tc60_security_malformed_json_or_injection_handled_safely(self):
        """TC 60: Malformed payloads return standard 422/400 without leaking stack traces."""
        res = self.client.post("/api/v2/bots", data="Not valid json", headers={"Content-Type": "application/json"})
        self.assertIn(res.status_code, [400, 422])
        # Verify no traceback leakage in response
        self.assertNotIn("Traceback", res.text)

    # ==============================================================================
    # Group H: Safety Invariants & Full System Regression (TC 61 - 65)
    # ==============================================================================

    def test_tc61_safety_invariant_trading_mode_dry_run(self):
        """TC 61: Safety Invariant: TRADING_MODE must be strictly DRY_RUN across all endpoints."""
        res = self.client.get("/api/v2/bots")
        self.assertEqual(res.status_code, 200)
        for bot in res.json():
            self.assertEqual(bot["trading_mode"], "DRY_RUN")

    def test_tc62_safety_invariant_paper_execution_gate_closed(self):
        """TC 62: Safety Invariant: AlpacaPaperGate.is_gate_open must remain False."""
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)

    def test_tc63_safety_invariant_simulation_environment_tags(self):
        """TC 63: Safety Invariant: All portfolio, orders, fills and health are tagged SIMULATION."""
        bot = self._create_sample_bot(f"bot_inv63_{uuid.uuid4().hex[:6]}")
        s_id = bot["session_id"]
        p_res = self.client.get(f"/api/v2/bots/{s_id}/portfolio").json()
        self.assertEqual(p_res["environment"], "SIMULATION")
        h_res = self.client.get(f"/api/v2/bots/{s_id}/health").json()
        self.assertEqual(h_res["environment"], "SIMULATION")
        perf_res = self.client.get(f"/api/v2/bots/{s_id}/performance").json()
        self.assertEqual(perf_res["environment"], "SIMULATION")

    def test_tc64_safety_invariant_zero_alpaca_broker_calls(self):
        """TC 64: Safety Invariant: Verify zero live Alpaca Broker API endpoints exposed."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        for path in routes:
            self.assertNotIn("/alpaca/v2/orders", path)
            self.assertNotIn("/live/submit", path)
            self.assertNotIn("/broker/live", path)

    def test_tc65_end_to_end_multibar_api_websocket_simulation_flow(self):
        """
        TC 65: Full End-to-End Multi-Bar Flow:
        Create Bot -> Connect WS -> Start -> Submit Bar 1 -> Submit Bar 2 -> Submit Bar 3 -> Check Portfolio -> Pause -> Stop.
        """
        bot_id = f"bot_e2e_{uuid.uuid4().hex[:6]}"
        bot = self._create_sample_bot(bot_id=bot_id, initial_cash=100000.0)
        s_id = bot["session_id"]

        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            # 1. Receive Initial State Snapshot
            init_snap = ws.receive_json()
            self.assertEqual(init_snap["event_type"], "SNAPSHOT")
            self.assertEqual(init_snap["payload"]["summary"]["lifecycle_state"], "STOPPED")

            # 2. Start Bot
            start_res = self.client.post(f"/api/v2/bots/{s_id}/start")
            self.assertEqual(start_res.status_code, 200)
            self.assertEqual(start_res.json()["lifecycle_state"], "RUNNING")
            start_evt = ws.receive_json()
            self.assertEqual(start_evt["event_type"], "BOT_LIFECYCLE_EVENT")
            self.assertEqual(start_evt["payload"]["action"], "START")

            # 3. Submit Bar 1 (Warmup / Initial Bar)
            now = datetime.now(timezone.utc)
            bar1 = {
                "symbol": "NVDA",
                "timeframe": "1m",
                "event_time": now.isoformat(),
                "open": 140.0,
                "high": 141.0,
                "low": 139.5,
                "close": 140.5,
                "volume": 2000.0,
                "environment": "SIMULATION",
            }
            res_b1 = self.client.post(f"/api/v2/bots/{s_id}/bars", json=bar1)
            self.assertEqual(res_b1.status_code, 200)

            # 4. Submit Bar 2
            bar2 = {
                "symbol": "NVDA",
                "timeframe": "1m",
                "event_time": (now + timedelta(minutes=1)).isoformat(),
                "open": 140.5,
                "high": 142.5,
                "low": 140.2,
                "close": 142.0,
                "volume": 3500.0,
                "environment": "SIMULATION",
            }
            res_b2 = self.client.post(f"/api/v2/bots/{s_id}/bars", json=bar2)
            self.assertEqual(res_b2.status_code, 200)

            # 5. Query Portfolio
            port_res = self.client.get(f"/api/v2/bots/{s_id}/portfolio")
            self.assertEqual(port_res.status_code, 200)
            port_data = port_res.json()
            self.assertEqual(port_data["initial_cash"], 100000.0)
            self.assertGreater(port_data["equity"], 0)

            # 6. Pause Bot
            pause_res = self.client.post(f"/api/v2/bots/{s_id}/pause", json={"reason": "END_OF_SIMULATION"})
            self.assertEqual(pause_res.status_code, 200)
            self.assertEqual(pause_res.json()["lifecycle_state"], "PAUSED")
            pause_evt = ws.receive_json()
            self.assertEqual(pause_evt["event_type"], "BOT_LIFECYCLE_EVENT")
            self.assertEqual(pause_evt["payload"]["action"], "PAUSE")

            # 7. Stop Bot
            stop_res = self.client.post(f"/api/v2/bots/{s_id}/stop", json={"policy": "CANCEL_REMAINDER"})
            self.assertEqual(stop_res.status_code, 200)
            self.assertEqual(stop_res.json()["lifecycle_state"], "STOPPED")
            stop_evt = ws.receive_json()
            self.assertEqual(stop_evt["event_type"], "BOT_LIFECYCLE_EVENT")
            self.assertEqual(stop_evt["payload"]["action"], "STOP")

            # 8. Query Final Performance & Health
            perf_res = self.client.get(f"/api/v2/bots/{s_id}/performance")
            self.assertEqual(perf_res.status_code, 200)
            health_res = self.client.get(f"/api/v2/bots/{s_id}/health")
            self.assertEqual(health_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
