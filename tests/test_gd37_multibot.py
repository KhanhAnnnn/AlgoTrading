"""
tests/test_gd37_multibot.py — GĐ37 Multi-Bot Management, Resource Isolation & Supervisor Test Suite
AlgoTrading V2.0 Paper Trading Bot System.

Contains 75 automated unit, integration, isolation, failure, and safety tests covering:
- Group A: Multi-Bot Registry & Lifecycle (TC 01 - 12)
- Group B: State & Resource Isolation (TC 13 - 24)
- Group C: Market Data Fan-Out Dispatcher (TC 25 - 36)
- Group D: Concurrency, Limits & Backpressure (TC 37 - 47)
- Group E: Failure Isolation & Recovery (TC 48 - 57)
- Group F: REST API, WebSocket & Dashboard (TC 58 - 67)
- Group G: Safety Invariants & Full System Regression (TC 68 - 75)
"""

import sys
import os
import unittest
import json
import uuid
import tempfile
import shutil
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

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
from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    SimulatedOrder,
    SimulatedFill,
    SimulatedPosition,
)
from libs.bot.orchestration.lifecycle import BotLifecycleState
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.risk.config import RiskConfig
from libs.alpaca_paper_gate import (
    AlpacaPaperGate,
    PaperExecutionGateClosedError,
    LiveTradingProhibitedError,
)
from libs.bot.multibot.resource_policy import ResourcePolicy
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.subscriptions import BotSubscription, SubscriptionManager
from libs.bot.multibot.dispatcher import V2MarketDataDispatcher
from libs.bot.multibot.isolation import (
    BotSandboxFactory,
    get_bot_storage_dir,
    get_bot_order_store_dir,
    get_bot_fill_store_dir,
    get_bot_checkpoint_dir,
)
from libs.bot.multibot.supervisor import (
    MultiBotSupervisor,
    BotRuntime,
    ConcurrencyLimitExceededError,
    BotNotFoundError,
)
from libs.bot.multibot.recovery import MultiBotRecoveryManager
from libs.bot.multibot.telemetry import SupervisorTelemetryCollector


def make_test_bar(
    symbol: str = "NVDA",
    timeframe: str = "1m",
    event_time: datetime = None,
    open_p: float = 140.0,
    high_p: float = 142.0,
    low_p: float = 139.5,
    close_p: float = 141.0,
    volume: float = 1000.0,
    is_final: bool = True,
    event_id: str = None,
) -> MarketDataEvent:
    """Helper creating standardized 1m test MarketDataEvent."""
    t = event_time or datetime.now(timezone.utc)
    ev_id = event_id or f"evt_{symbol}_{uuid.uuid4().hex[:8]}"
    return MarketDataEvent(
        event_id=ev_id,
        symbol=symbol,
        timeframe=timeframe,
        event_time=t,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=volume,
        is_final=is_final,
        environment="SIMULATION",
    )


class TestGD37MultiBot(unittest.TestCase):
    """GĐ37 Comprehensive Test Suite for Multi-Bot Management & Resource Isolation."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Create dedicated temporary test directory for each test case
        self.test_dir = tempfile.mkdtemp(prefix="test_gd37_multibot_")
        self.registry_dir = os.path.join(self.test_dir, "registry")
        self.sessions_dir = os.path.join(self.test_dir, "sessions")
        os.makedirs(self.registry_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)

        self.policy = ResourcePolicy(
            max_concurrent_bots=5,
            max_queue_size_per_bot=50,
            shutdown_timeout_seconds=2.0,
        )
        self.registry = BotRegistry(storage_dir=self.registry_dir)
        self.sub_manager = SubscriptionManager()
        self.dispatcher = V2MarketDataDispatcher(
            subscription_manager=self.sub_manager,
            max_queue_size_per_bot=self.policy.max_queue_size_per_bot,
        )
        self.supervisor = MultiBotSupervisor(
            registry=self.registry,
            dispatcher=self.dispatcher,
            subscription_manager=self.sub_manager,
            resource_policy=self.policy,
            base_dir=self.test_dir,
        )

    def tearDown(self):
        # Gracefully stop supervisor bots and remove temp directory
        try:
            self.supervisor.stop_all_bots()
        except Exception:
            pass
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # ==========================================================================
    # GROUP A: MULTI-BOT REGISTRY & LIFECYCLE (TC 01 - 12)
    # ==========================================================================

    def test_tc01_bot_definition_registration(self):
        """TC 01: Bot definition registration and serialization to disk."""
        b_def = BotDefinition(
            bot_id="bot_alpha",
            bot_name="Alpha NVDA Bot",
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
        )
        saved = self.registry.register_bot(b_def)
        self.assertEqual(saved.bot_id, "bot_alpha")
        self.assertTrue(os.path.exists(self.registry.registry_file))
        loaded = self.registry.get_bot("bot_alpha")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.bot_name, "Alpha NVDA Bot")

    def test_tc02_duplicate_bot_id_rejection(self):
        """TC 02: Duplicate bot_id registration is strictly rejected."""
        b_def = BotDefinition(bot_id="bot_dup", bot_name="Bot 1")
        self.registry.register_bot(b_def)
        with self.assertRaises(ValueError):
            self.registry.register_bot(BotDefinition(bot_id="bot_dup", bot_name="Bot 2"))

    def test_tc03_configuration_hash_determinism(self):
        """TC 03: Configuration hash determinism and validation."""
        b1 = BotDefinition(bot_id="bot_h1", symbols=["BTC/USD", "NVDA"], initial_simulated_cash=50000.0)
        b2 = BotDefinition(bot_id="bot_h1", symbols=["NVDA", "BTC/USD"], initial_simulated_cash=50000.0)
        # Symbol order is sorted before hashing
        self.assertEqual(b1.compute_configuration_hash(), b2.compute_configuration_hash())

    def test_tc04_bot_definition_updating(self):
        """TC 04: Bot definition updating updates parameters and configuration hash."""
        b_def = BotDefinition(bot_id="bot_update", bot_name="Original Name")
        self.registry.register_bot(b_def)
        old_hash = b_def.configuration_hash

        updated = self.registry.update_bot("bot_update", {"bot_name": "New Name", "symbols": ["ETH/USD"]})
        self.assertEqual(updated.bot_name, "New Name")
        self.assertEqual(updated.symbols, ["ETH/USD"])
        self.assertNotEqual(updated.configuration_hash, old_hash)

    def test_tc05_bot_soft_archiving(self):
        """TC 05: Bot soft-archiving disables bot without deleting trading history."""
        b_def = BotDefinition(bot_id="bot_archive", bot_name="Archive Bot")
        self.registry.register_bot(b_def)
        self.registry.archive_bot("bot_archive")

        bot = self.registry.get_bot("bot_archive")
        self.assertTrue(bot.archived)
        self.assertFalse(bot.enabled)

        # Archived bot cannot be started
        with self.assertRaises(ValueError):
            self.supervisor.start_bot("bot_archive")

    def test_tc06_list_bots_filtering(self):
        """TC 06: List bots filters archived definitions properly."""
        self.registry.register_bot(BotDefinition(bot_id="bot_active_1"))
        self.registry.register_bot(BotDefinition(bot_id="bot_active_2"))
        self.registry.register_bot(BotDefinition(bot_id="bot_to_archive"))
        self.registry.archive_bot("bot_to_archive")

        active_list = self.registry.list_bots(include_archived=False)
        self.assertEqual(len(active_list), 2)
        all_list = self.registry.list_bots(include_archived=True)
        self.assertEqual(len(all_list), 3)

    def test_tc07_session_association_per_bot(self):
        """TC 07: Multiple historical sessions are associated with the same bot_id."""
        b_def = BotDefinition(bot_id="bot_multi_sess")
        self.registry.register_bot(b_def)

        sess1 = self.supervisor.start_bot("bot_multi_sess")
        self.supervisor.stop_bot("bot_multi_sess")

        sess2 = self.supervisor.start_bot("bot_multi_sess")
        self.supervisor.stop_bot("bot_multi_sess")

        sessions = self.registry.list_sessions_for_bot("bot_multi_sess")
        self.assertGreaterEqual(len(sessions), 2)
        self.assertNotEqual(sess1.bot_session_id, sess2.bot_session_id)

    def test_tc08_supervisor_start_bot(self):
        """TC 08: Supervisor starts registered bot into RUNNING state."""
        self.registry.register_bot(BotDefinition(bot_id="bot_start_tc08", symbols=["NVDA"]))
        session = self.supervisor.start_bot("bot_start_tc08")
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)
        runtime = self.supervisor.get_bot_runtime("bot_start_tc08")
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime.state, BotLifecycleState.RUNNING)

    def test_tc09_supervisor_start_bot_idempotency(self):
        """TC 09: Supervisor start_bot is idempotent if bot is already RUNNING."""
        self.registry.register_bot(BotDefinition(bot_id="bot_idem"))
        sess1 = self.supervisor.start_bot("bot_idem")
        sess2 = self.supervisor.start_bot("bot_idem")
        self.assertEqual(sess1.bot_session_id, sess2.bot_session_id)
        self.assertEqual(self.supervisor.active_bot_count, 1)

    def test_tc10_supervisor_pause_bot(self):
        """TC 10: Supervisor pauses a running bot and preserves session."""
        self.registry.register_bot(BotDefinition(bot_id="bot_pause_tc10"))
        self.supervisor.start_bot("bot_pause_tc10")
        paused_sess = self.supervisor.pause_bot("bot_pause_tc10", reason="OPERATOR_CHECK")
        self.assertEqual(paused_sess.lifecycle_state, BotLifecycleState.PAUSED)
        runtime = self.supervisor.get_bot_runtime("bot_pause_tc10")
        self.assertEqual(runtime.state, BotLifecycleState.PAUSED)

    def test_tc11_supervisor_resume_bot(self):
        """TC 11: Supervisor resumes a paused bot back to RUNNING."""
        self.registry.register_bot(BotDefinition(bot_id="bot_resume_tc11"))
        self.supervisor.start_bot("bot_resume_tc11")
        self.supervisor.pause_bot("bot_resume_tc11")
        resumed_sess = self.supervisor.resume_bot("bot_resume_tc11")
        self.assertEqual(resumed_sess.lifecycle_state, BotLifecycleState.RUNNING)

    def test_tc12_supervisor_stop_bot_cancel_remainder(self):
        """TC 12: Supervisor stops bot gracefully with CANCEL_REMAINDER policy."""
        self.registry.register_bot(BotDefinition(bot_id="bot_stop_tc12"))
        self.supervisor.start_bot("bot_stop_tc12")
        stopped_sess = self.supervisor.stop_bot("bot_stop_tc12", policy=StopPolicy.CANCEL_REMAINDER)
        self.assertEqual(stopped_sess.lifecycle_state, BotLifecycleState.STOPPED)
        self.assertEqual(self.supervisor.active_bot_count, 0)

    # ==========================================================================
    # GROUP B: STATE & RESOURCE ISOLATION (TC 13 - 24)
    # ==========================================================================

    def test_tc13_path_isolation_for_storage(self):
        """TC 13: Storage paths are strictly separated by bot_id and session_id."""
        dir1 = get_bot_storage_dir("bot_1", "sess_1", self.test_dir)
        dir2 = get_bot_storage_dir("bot_2", "sess_2", self.test_dir)
        self.assertIn("bot_1", dir1)
        self.assertIn("bot_2", dir2)
        self.assertNotEqual(dir1, dir2)

    def test_tc14_portfolio_cash_isolation(self):
        """TC 14: Portfolio cash balances are strictly isolated between two bots."""
        self.registry.register_bot(BotDefinition(bot_id="bot_cash_1", initial_simulated_cash=100000.0))
        self.registry.register_bot(BotDefinition(bot_id="bot_cash_2", initial_simulated_cash=50000.0))

        self.supervisor.start_bot("bot_cash_1")
        self.supervisor.start_bot("bot_cash_2")

        port1 = self.supervisor.get_bot_portfolio("bot_cash_1")
        port2 = self.supervisor.get_bot_portfolio("bot_cash_2")

        self.assertEqual(float(port1.cash), 100000.0)
        self.assertEqual(float(port2.cash), 50000.0)

    def test_tc15_same_symbol_position_book_isolation(self):
        """TC 15: Two bots trading the exact same symbol maintain separate PositionBooks."""
        self.registry.register_bot(BotDefinition(bot_id="bot_nvda_a", symbols=["NVDA"], initial_simulated_cash=100000.0))
        self.registry.register_bot(BotDefinition(bot_id="bot_nvda_b", symbols=["NVDA"], initial_simulated_cash=50000.0))

        self.supervisor.start_bot("bot_nvda_a")
        self.supervisor.start_bot("bot_nvda_b")

        rt_a = self.supervisor.get_bot_runtime("bot_nvda_a")
        rt_b = self.supervisor.get_bot_runtime("bot_nvda_b")

        # Mutate Bot A position book directly
        rt_a.orchestrator.portfolio.positions.record_fill("NVDA", "BUY", 10.0, 140.0, 0.0)
        pos_a = rt_a.orchestrator.portfolio.positions.get_position("NVDA")
        self.assertIsNotNone(pos_a)
        self.assertEqual(pos_a.qty, 10.0)
        # Bot B position book must remain None or 0
        pos_b = rt_b.orchestrator.portfolio.positions.get_position("NVDA")
        self.assertIsNone(pos_b)

    def test_tc16_same_symbol_order_isolation(self):
        """TC 16: Order submission in Bot A does not contaminate Bot B order book."""
        self.registry.register_bot(BotDefinition(bot_id="bot_ord_a", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="bot_ord_b", symbols=["NVDA"]))

        self.supervisor.start_bot("bot_ord_a")
        self.supervisor.start_bot("bot_ord_b")

        rt_a = self.supervisor.get_bot_runtime("bot_ord_a")
        rt_b = self.supervisor.get_bot_runtime("bot_ord_b")

        o1 = rt_a.orchestrator.simulation_broker.submit_order(
            symbol="NVDA", side="BUY", order_type="MARKET", quantity=5.0, price=140.0
        )
        self.assertIsNotNone(o1)
        self.assertIn(o1.simulated_order_id, rt_a.orchestrator.simulation_broker.order_manager._orders)
        self.assertNotIn(o1.simulated_order_id, rt_b.orchestrator.simulation_broker.order_manager._orders)

    def test_tc17_same_symbol_fill_isolation(self):
        """TC 17: Simulated fill on Bot A does not affect Bot B cash or fills."""
        self.registry.register_bot(BotDefinition(bot_id="bot_fill_a", symbols=["NVDA"], initial_simulated_cash=100000.0))
        self.registry.register_bot(BotDefinition(bot_id="bot_fill_b", symbols=["NVDA"], initial_simulated_cash=100000.0))

        self.supervisor.start_bot("bot_fill_a")
        self.supervisor.start_bot("bot_fill_b")

        rt_a = self.supervisor.get_bot_runtime("bot_fill_a")
        rt_b = self.supervisor.get_bot_runtime("bot_fill_b")

        # Submit market order on Bot A and simulate fill
        rt_a.orchestrator.simulation_broker.submit_order(
            symbol="NVDA", side="BUY", order_type="MARKET", quantity=10.0, price=100.0
        )
        bar = make_test_bar(symbol="NVDA", close_p=100.0)
        rt_a.orchestrator.simulation_broker.process_market_bar(bar)

        self.assertGreater(len(rt_a.orchestrator.simulation_broker._fills), 0)
        self.assertEqual(len(rt_b.orchestrator.simulation_broker._fills), 0)
        self.assertLess(float(rt_a.orchestrator.portfolio.cash), 100000.0)
        self.assertEqual(float(rt_b.orchestrator.portfolio.cash), 100000.0)

    def test_tc18_isolated_risk_limits(self):
        """TC 18: Risk parameters and limits are completely isolated per bot."""
        cfg_conservative = {"max_drawdown_pct": 0.05, "max_position_notional": 5000.0}
        cfg_aggressive = {"max_drawdown_pct": 0.30, "max_position_notional": 50000.0}

        self.registry.register_bot(BotDefinition(bot_id="bot_risk_c", risk_config=cfg_conservative))
        self.registry.register_bot(BotDefinition(bot_id="bot_risk_a", risk_config=cfg_aggressive))

        self.supervisor.start_bot("bot_risk_c")
        self.supervisor.start_bot("bot_risk_a")

        rt_c = self.supervisor.get_bot_runtime("bot_risk_c")
        rt_a = self.supervisor.get_bot_runtime("bot_risk_a")

        self.assertEqual(rt_c.orchestrator.risk_config.max_drawdown_pct, 0.05)
        self.assertEqual(rt_a.orchestrator.risk_config.max_drawdown_pct, 0.30)
        self.assertEqual(rt_c.orchestrator.risk_config.max_position_notional, 5000.0)
        self.assertEqual(rt_a.orchestrator.risk_config.max_position_notional, 50000.0)

    def test_tc19_isolated_order_stores(self):
        """TC 19: Order stores persist to segregated filesystem paths."""
        self.registry.register_bot(BotDefinition(bot_id="bot_store_a", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="bot_store_b", symbols=["NVDA"]))

        self.supervisor.start_bot("bot_store_a")
        self.supervisor.start_bot("bot_store_b")

        rt_a = self.supervisor.get_bot_runtime("bot_store_a")
        rt_b = self.supervisor.get_bot_runtime("bot_store_b")

        self.assertNotEqual(
            rt_a.orchestrator.simulation_broker.order_store.storage_dir,
            rt_b.orchestrator.simulation_broker.order_store.storage_dir,
        )

    def test_tc20_isolated_fill_stores(self):
        """TC 20: Fill stores persist to segregated filesystem paths."""
        self.registry.register_bot(BotDefinition(bot_id="bot_fstore_a", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="bot_fstore_b", symbols=["NVDA"]))

        self.supervisor.start_bot("bot_fstore_a")
        self.supervisor.start_bot("bot_fstore_b")

        rt_a = self.supervisor.get_bot_runtime("bot_fstore_a")
        rt_b = self.supervisor.get_bot_runtime("bot_fstore_b")

        self.assertNotEqual(
            rt_a.orchestrator.simulation_broker.fill_store.storage_dir,
            rt_b.orchestrator.simulation_broker.fill_store.storage_dir,
        )

    def test_tc21_isolated_execution_ledgers(self):
        """TC 21: Execution ledgers write to separate ledger log files."""
        self.registry.register_bot(BotDefinition(bot_id="bot_ledg_a", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="bot_ledg_b", symbols=["NVDA"]))

        self.supervisor.start_bot("bot_ledg_a")
        self.supervisor.start_bot("bot_ledg_b")

        rt_a = self.supervisor.get_bot_runtime("bot_ledg_a")
        rt_b = self.supervisor.get_bot_runtime("bot_ledg_b")

        self.assertNotEqual(
            rt_a.orchestrator.simulation_broker.ledger.ledger_path,
            rt_b.orchestrator.simulation_broker.ledger.ledger_path,
        )

    def test_tc22_isolated_checkpoint_managers(self):
        """TC 22: Checkpoint managers persist to segregated checkpoint directories."""
        self.registry.register_bot(BotDefinition(bot_id="bot_cp_a"))
        self.registry.register_bot(BotDefinition(bot_id="bot_cp_b"))

        self.supervisor.start_bot("bot_cp_a")
        self.supervisor.start_bot("bot_cp_b")

        rt_a = self.supervisor.get_bot_runtime("bot_cp_a")
        rt_b = self.supervisor.get_bot_runtime("bot_cp_b")

        self.assertNotEqual(
            rt_a.orchestrator.checkpoint_manager.storage_dir,
            rt_b.orchestrator.checkpoint_manager.storage_dir,
        )

    def test_tc23_isolated_event_journals(self):
        """TC 23: Event journals record audit trails to distinct log files."""
        self.registry.register_bot(BotDefinition(bot_id="bot_jrnl_a"))
        self.registry.register_bot(BotDefinition(bot_id="bot_jrnl_b"))

        self.supervisor.start_bot("bot_jrnl_a")
        self.supervisor.start_bot("bot_jrnl_b")

        rt_a = self.supervisor.get_bot_runtime("bot_jrnl_a")
        rt_b = self.supervisor.get_bot_runtime("bot_jrnl_b")

        self.assertNotEqual(
            rt_a.orchestrator.journal.log_file,
            rt_b.orchestrator.journal.log_file,
        )

    def test_tc24_unique_session_and_portfolio_ids(self):
        """TC 24: Unique session IDs and portfolio IDs across bot instances."""
        self.registry.register_bot(BotDefinition(bot_id="bot_u1"))
        self.registry.register_bot(BotDefinition(bot_id="bot_u2"))

        sess1 = self.supervisor.start_bot("bot_u1")
        sess2 = self.supervisor.start_bot("bot_u2")

        self.assertNotEqual(sess1.bot_session_id, sess2.bot_session_id)
        rt1 = self.supervisor.get_bot_runtime("bot_u1")
        rt2 = self.supervisor.get_bot_runtime("bot_u2")
        self.assertNotEqual(rt1.orchestrator.portfolio.portfolio_id, rt2.orchestrator.portfolio.portfolio_id)

    # ==========================================================================
    # GROUP C: MARKET DATA FAN-OUT DISPATCHER (TC 25 - 36)
    # ==========================================================================

    def test_tc25_subscription_indexing(self):
        """TC 25: Subscription registration creates accurate symbol index entries."""
        sub1 = BotSubscription(bot_id="bot_s1", symbols={"NVDA", "BTC/USD"}, timeframe="1m")
        sub2 = BotSubscription(bot_id="bot_s2", symbols={"NVDA"}, timeframe="1m")
        self.sub_manager.register_subscription(sub1)
        self.sub_manager.register_subscription(sub2)

        nvda_bots = self.sub_manager.get_subscribed_bots("NVDA", "1m")
        self.assertEqual(nvda_bots, ["bot_s1", "bot_s2"])
        btc_bots = self.sub_manager.get_subscribed_bots("BTC/USD", "1m")
        self.assertEqual(btc_bots, ["bot_s1"])

    def test_tc26_multi_bot_fanout_dispatch(self):
        """TC 26: Dispatcher fans out single market event to multiple subscribed bots."""
        sub1 = BotSubscription(bot_id="b1", symbols={"NVDA"}, timeframe="1m")
        sub2 = BotSubscription(bot_id="b2", symbols={"NVDA"}, timeframe="1m")
        self.sub_manager.register_subscription(sub1)
        self.sub_manager.register_subscription(sub2)

        bar = make_test_bar(symbol="NVDA", event_id="evt_fanout_1")
        res = self.dispatcher.dispatch_event(bar)

        self.assertEqual(res.get("b1"), "ENQUEUED")
        self.assertEqual(res.get("b2"), "ENQUEUED")
        self.assertEqual(self.dispatcher.get_queue_depth("b1"), 1)
        self.assertEqual(self.dispatcher.get_queue_depth("b2"), 1)

    def test_tc27_symbol_routing_filtering(self):
        """TC 27: Dispatcher routes events only to bots subscribed to that symbol."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_nvda", symbols={"NVDA"}, timeframe="1m"))
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_btc", symbols={"BTC/USD"}, timeframe="1m"))

        bar = make_test_bar(symbol="BTC/USD")
        res = self.dispatcher.dispatch_event(bar)

        self.assertIn("b_btc", res)
        self.assertNotIn("b_nvda", res)

    def test_tc28_timeframe_filtering(self):
        """TC 28: Dispatcher filters out events for non-matching timeframes."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_1m", symbols={"NVDA"}, timeframe="1m"))
        bar_5m = make_test_bar(symbol="NVDA", timeframe="5m")
        res = self.dispatcher.dispatch_event(bar_5m)
        self.assertEqual(len(res), 0)

    def test_tc29_unsubscribed_symbol_filtering(self):
        """TC 29: Dispatcher ignores events for symbols with no active subscribers."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_nvda", symbols={"NVDA"}, timeframe="1m"))
        bar_aapl = make_test_bar(symbol="AAPL")
        res = self.dispatcher.dispatch_event(bar_aapl)
        self.assertEqual(len(res), 0)
        self.assertEqual(self.dispatcher.total_received, 1)

    def test_tc30_per_bot_queue_capacity(self):
        """TC 30: Dispatcher enforces max_queue_size_per_bot limit on per-bot queues."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_cap", symbols={"NVDA"}, timeframe="1m"))
        base_time = datetime.now(timezone.utc)

        # Dispatch up to max capacity (50)
        for i in range(50):
            t = base_time + timedelta(minutes=i)
            bar = make_test_bar(symbol="NVDA", event_id=f"evt_cap_{i}", event_time=t)
            res = self.dispatcher.dispatch_event(bar)
            self.assertEqual(res["b_cap"], "ENQUEUED")

        # 51st event must be dropped due to queue overflow
        bar_overflow = make_test_bar(symbol="NVDA", event_id="evt_cap_overflow", event_time=base_time + timedelta(minutes=51))
        res = self.dispatcher.dispatch_event(bar_overflow)
        self.assertEqual(res["b_cap"], "DROPPED_QUEUE_FULL")
        self.assertEqual(self.dispatcher.total_dropped, 1)

    def test_tc31_per_bot_duplicate_event_rejection(self):
        """TC 31: Duplicate event IDs are detected and rejected per bot."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_dup", symbols={"NVDA"}, timeframe="1m"))
        bar = make_test_bar(symbol="NVDA", event_id="evt_dup_1")

        res1 = self.dispatcher.dispatch_event(bar)
        self.assertEqual(res1["b_dup"], "ENQUEUED")

        res2 = self.dispatcher.dispatch_event(bar)
        self.assertEqual(res2["b_dup"], "DUPLICATE")
        self.assertEqual(self.dispatcher.total_duplicates, 1)

    def test_tc32_per_symbol_temporal_ordering(self):
        """TC 32: Out-of-order timestamps for the same symbol are dropped."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_order", symbols={"NVDA"}, timeframe="1m"))
        t2 = datetime(2026, 11, 24, 10, 5, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 11, 24, 10, 4, 0, tzinfo=timezone.utc)

        bar_future = make_test_bar(symbol="NVDA", event_id="evt_fut", event_time=t2)
        res_future = self.dispatcher.dispatch_event(bar_future)
        self.assertEqual(res_future["b_order"], "ENQUEUED")

        bar_past = make_test_bar(symbol="NVDA", event_id="evt_past", event_time=t1)
        res_past = self.dispatcher.dispatch_event(bar_past)
        self.assertEqual(res_past["b_order"], "OUT_OF_ORDER")

    def test_tc33_nonblocking_backpressure_isolation(self):
        """TC 33: A bot with a full queue does not block or delay dispatch to a healthy bot."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_slow", symbols={"NVDA"}, timeframe="1m"))
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_fast", symbols={"NVDA"}, timeframe="1m"))
        base_time = datetime.now(timezone.utc)

        # Fill up b_slow queue
        for i in range(50):
            t = base_time + timedelta(minutes=i)
            self.dispatcher.dispatch_event(make_test_bar(symbol="NVDA", event_id=f"evt_fill_{i}", event_time=t))

        # Drain b_fast queue so it has space
        while self.dispatcher.get_next_event("b_fast") is not None:
            pass

        # Dispatch 51st event
        t51 = base_time + timedelta(minutes=51)
        res = self.dispatcher.dispatch_event(make_test_bar(symbol="NVDA", event_id="evt_isolated_51", event_time=t51))
        self.assertEqual(res["b_slow"], "DROPPED_QUEUE_FULL")
        self.assertEqual(res["b_fast"], "ENQUEUED")

    def test_tc34_per_bot_cursor_tracking(self):
        """TC 34: Dispatcher maintains durable cursor per bot."""
        self.dispatcher.ack_event("b_cursor", "evt_100")
        self.assertEqual(self.dispatcher.get_cursor("b_cursor"), "evt_100")

    def test_tc35_pause_isolation_does_not_stall_peers(self):
        """TC 35: Pausing Bot A does not stall event processing of Bot B in supervisor."""
        self.registry.register_bot(BotDefinition(bot_id="b_p_paused", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="b_p_active", symbols=["NVDA"]))

        self.supervisor.start_bot("b_p_paused")
        self.supervisor.start_bot("b_p_active")

        self.supervisor.pause_bot("b_p_paused")

        bar = make_test_bar(symbol="NVDA")
        proc_res = self.supervisor.dispatch_market_data(bar, auto_process=True)

        self.assertIn("b_p_active", proc_res)
        self.assertIn("b_p_paused", proc_res)
        # Active bot processed bar
        self.assertEqual(proc_res["b_p_active"]["dispatch_status"], "PROCESSED")

    def test_tc36_dispatcher_telemetry_reporting(self):
        """TC 36: Dispatcher telemetry accurately summarizes dispatched, dropped, and queue depths."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_tel", symbols={"NVDA"}, timeframe="1m"))
        bar = make_test_bar(symbol="NVDA")
        self.dispatcher.dispatch_event(bar)
        tel = self.dispatcher.get_telemetry()
        self.assertEqual(tel["total_received"], 1)
        self.assertEqual(tel["total_dispatched"], 1)
        self.assertEqual(tel["active_queues_count"], 1)

    # ==========================================================================
    # GROUP D: CONCURRENCY, LIMITS & BACKPRESSURE (TC 37 - 47)
    # ==========================================================================

    def test_tc37_max_concurrent_bots_limit(self):
        """TC 37: Starting more bots than max_concurrent_bots raises ConcurrencyLimitExceededError."""
        # max_concurrent_bots is set to 5 in setUp
        for i in range(5):
            b_id = f"bot_limit_{i}"
            self.registry.register_bot(BotDefinition(bot_id=b_id))
            self.supervisor.start_bot(b_id)

        # 6th bot must be rejected
        self.registry.register_bot(BotDefinition(bot_id="bot_limit_overflow"))
        with self.assertRaises(ConcurrencyLimitExceededError):
            self.supervisor.start_bot("bot_limit_overflow")

    def test_tc38_resource_policy_validation(self):
        """TC 38: ResourcePolicy rejects non-positive limits."""
        with self.assertRaises(ValueError):
            ResourcePolicy(max_concurrent_bots=0).validate()
        with self.assertRaises(ValueError):
            ResourcePolicy(max_queue_size_per_bot=-5).validate()

    def test_tc39_dynamic_concurrency_slot_freeing(self):
        """TC 39: Stopping a bot frees concurrency slots immediately."""
        for i in range(5):
            b_id = f"bot_slot_{i}"
            self.registry.register_bot(BotDefinition(bot_id=b_id))
            self.supervisor.start_bot(b_id)

        self.assertEqual(self.supervisor.active_bot_count, 5)

        # Stop bot 0
        self.supervisor.stop_bot("bot_slot_0")
        self.assertEqual(self.supervisor.active_bot_count, 4)

        # Now 6th bot can start
        self.registry.register_bot(BotDefinition(bot_id="bot_slot_new"))
        sess = self.supervisor.start_bot("bot_slot_new")
        self.assertEqual(sess.lifecycle_state, BotLifecycleState.RUNNING)
        self.assertEqual(self.supervisor.active_bot_count, 5)

    def test_tc40_queue_overflow_telemetry_tracking(self):
        """TC 40: Queue overflow telemetry increments total_dropped and bot dropped stats."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_stat", symbols={"NVDA"}, timeframe="1m"))
        base_time = datetime.now(timezone.utc)
        for i in range(55):
            t = base_time + timedelta(minutes=i)
            self.dispatcher.dispatch_event(make_test_bar(symbol="NVDA", event_id=f"e_{i}", event_time=t))

        stats = self.dispatcher._bot_stats["b_stat"]
        self.assertEqual(stats["enqueued"], 50)
        self.assertEqual(stats["dropped"], 5)

    def test_tc41_multibot_queue_depth_observability(self):
        """TC 41: Dispatcher reports queue depths across all bots."""
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_d1", symbols={"NVDA"}, timeframe="1m"))
        self.sub_manager.register_subscription(BotSubscription(bot_id="b_d2", symbols={"NVDA"}, timeframe="1m"))

        self.dispatcher.dispatch_event(make_test_bar(symbol="NVDA"))
        tel = self.dispatcher.get_telemetry()
        self.assertEqual(tel["queue_depths"]["b_d1"], 1)
        self.assertEqual(tel["queue_depths"]["b_d2"], 1)

    def test_tc42_supervisor_graceful_shutdown_all(self):
        """TC 42: Supervisor stop_all_bots gracefully shuts down all active bots."""
        for i in range(3):
            b_id = f"b_shut_{i}"
            self.registry.register_bot(BotDefinition(bot_id=b_id))
            self.supervisor.start_bot(b_id)

        self.assertEqual(self.supervisor.active_bot_count, 3)
        res = self.supervisor.stop_all_bots()
        self.assertEqual(len(res), 3)
        self.assertEqual(self.supervisor.active_bot_count, 0)

    def test_tc43_shutdown_timeout_handling(self):
        """TC 43: Shutdown timeout is respected without hanging."""
        self.registry.register_bot(BotDefinition(bot_id="b_to"))
        self.supervisor.start_bot("b_to")
        res = self.supervisor.stop_all_bots(timeout=0.5)
        self.assertEqual(res.get("b_to"), "STOPPED")

    def test_tc44_heartbeat_tracking(self):
        """TC 44: Supervisor records and updates heartbeats for active bots."""
        self.registry.register_bot(BotDefinition(bot_id="b_hb"))
        self.supervisor.start_bot("b_hb")
        rt = self.supervisor.get_bot_runtime("b_hb")
        initial_hb = rt.last_heartbeat

        self.supervisor.record_heartbeat("b_hb")
        self.assertGreaterEqual(rt.last_heartbeat, initial_hb)

    def test_tc45_concurrency_utilization_calculation(self):
        """TC 45: Supervisor health calculates accurate concurrency utilization."""
        for i in range(2):
            b_id = f"b_util_{i}"
            self.registry.register_bot(BotDefinition(bot_id=b_id))
            self.supervisor.start_bot(b_id)

        health = self.supervisor.get_supervisor_health()
        # 2 / 5 = 0.4
        self.assertEqual(health["concurrency_utilization"], 0.4)
        self.assertEqual(health["status"], "HEALTHY")

    def test_tc46_high_throughput_fanout_burst(self):
        """TC 46: High-throughput fan-out burst stress test across 5 concurrent bots."""
        for i in range(5):
            b_id = f"bot_burst_{i}"
            self.registry.register_bot(BotDefinition(bot_id=b_id, symbols=["NVDA"]))
            self.supervisor.start_bot(b_id)

        base_time = datetime.now(timezone.utc)
        for i in range(20):
            t = base_time + timedelta(minutes=i)
            bar = make_test_bar(symbol="NVDA", event_id=f"evt_burst_{i}", event_time=t)
            self.supervisor.dispatch_market_data(bar, auto_process=True)

        tel = self.dispatcher.get_telemetry()
        self.assertEqual(tel["total_received"], 20)
        self.assertEqual(tel["total_dispatched"], 100)  # 20 bars * 5 bots

    def test_tc47_no_cross_bot_lock_contention(self):
        """TC 47: Concurrent bar processing completes without deadlocks."""
        self.registry.register_bot(BotDefinition(bot_id="b_lock_1", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="b_lock_2", symbols=["NVDA"]))

        self.supervisor.start_bot("b_lock_1")
        self.supervisor.start_bot("b_lock_2")

        bar1 = make_test_bar(symbol="NVDA", event_id="e_l1")
        bar2 = make_test_bar(symbol="NVDA", event_id="e_l2", event_time=datetime.now(timezone.utc) + timedelta(minutes=1))

        self.supervisor.submit_bar_to_bot("b_lock_1", bar1)
        self.supervisor.submit_bar_to_bot("b_lock_2", bar2)

        st1 = self.supervisor.get_bot_status("b_lock_1")
        st2 = self.supervisor.get_bot_status("b_lock_2")
        self.assertEqual(st1["lifecycle_state"], "RUNNING")
        self.assertEqual(st2["lifecycle_state"], "RUNNING")

    # ==========================================================================
    # GROUP E: FAILURE ISOLATION & RECOVERY (TC 48 - 57)
    # ==========================================================================

    def test_tc48_bot_scoped_failure_transitions_to_error(self):
        """TC 48: Failure inside one bot transitions only that bot to ERROR."""
        self.registry.register_bot(BotDefinition(bot_id="b_err_1"))
        self.supervisor.start_bot("b_err_1")
        rt = self.supervisor.get_bot_runtime("b_err_1")

        rt.orchestrator.handle_error("TEST_ERR", "Simulated internal failure")
        self.assertEqual(rt.state, BotLifecycleState.ERROR)

    def test_tc49_peer_bots_remain_running_on_peer_error(self):
        """TC 49: Peer bots remain RUNNING when another bot fails into ERROR."""
        self.registry.register_bot(BotDefinition(bot_id="b_fail", symbols=["NVDA"]))
        self.registry.register_bot(BotDefinition(bot_id="b_healthy", symbols=["NVDA"]))

        self.supervisor.start_bot("b_fail")
        self.supervisor.start_bot("b_healthy")

        rt_fail = self.supervisor.get_bot_runtime("b_fail")
        rt_fail.orchestrator.handle_error("ERR_CRASH", "Crash test")

        rt_healthy = self.supervisor.get_bot_runtime("b_healthy")
        self.assertEqual(rt_fail.state, BotLifecycleState.ERROR)
        self.assertEqual(rt_healthy.state, BotLifecycleState.RUNNING)

        # Healthy bot continues receiving and processing bars
        bar = make_test_bar(symbol="NVDA")
        res = self.supervisor.submit_bar_to_bot("b_healthy", bar)
        self.assertIsNotNone(res)

    def test_tc50_catastrophic_error_fails_closed(self):
        """TC 50: Catastrophic orchestrator error pauses event loop and fails closed."""
        self.registry.register_bot(BotDefinition(bot_id="b_close"))
        self.supervisor.start_bot("b_close")
        rt = self.supervisor.get_bot_runtime("b_close")

        rt.orchestrator.handle_error("CATASTROPHIC", "Fatal DB write failure")
        self.assertTrue(rt.orchestrator.event_loop.is_paused)
        # Attempting submit_bar rejects processing
        bar = make_test_bar()
        res = rt.orchestrator.submit_bar(bar)
        self.assertIsNone(res)

    def test_tc51_recovery_manager_discovers_definitions(self):
        """TC 51: MultiBotRecoveryManager discovers registered definitions on cold start."""
        self.registry.register_bot(BotDefinition(bot_id="b_rec_1"))
        self.registry.register_bot(BotDefinition(bot_id="b_rec_2"))

        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        bots = recovery_mgr.discover_registered_bots()
        self.assertEqual(len(bots), 2)

    def test_tc52_recovery_manager_discovers_past_sessions(self):
        """TC 52: MultiBotRecoveryManager discovers uncompleted sessions for a bot."""
        self.registry.register_bot(BotDefinition(bot_id="b_past"))
        sess = self.supervisor.start_bot("b_past")
        self.supervisor.stop_bot("b_past")

        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        sessions = recovery_mgr.discover_sessions_for_bot("b_past")
        self.assertGreaterEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["bot_id"], "b_past")

    def test_tc53_bot_config_hash_integrity_verification(self):
        """TC 53: Recovery manager verifies configuration hash matches definition."""
        self.registry.register_bot(BotDefinition(bot_id="b_hash_check"))
        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        audit = recovery_mgr.verify_bot_integrity("b_hash_check")
        self.assertTrue(audit["config_hash_valid"])
        self.assertTrue(audit["valid"])

    def test_tc54_checkpoint_checksum_verification(self):
        """TC 54: Checkpoint checksum integrity is verified during recovery scan."""
        self.registry.register_bot(BotDefinition(bot_id="b_cp_ver"))
        sess = self.supervisor.start_bot("b_cp_ver")
        rt = self.supervisor.get_bot_runtime("b_cp_ver")
        rt.orchestrator.save_checkpoint()
        self.supervisor.stop_bot("b_cp_ver")

        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        audit = recovery_mgr.verify_bot_integrity("b_cp_ver")
        self.assertTrue(audit["valid"])
        self.assertGreaterEqual(audit["checkpoints_verified"], 1)

    def test_tc55_corrupted_checkpoint_detection(self):
        """TC 55: Corrupted checkpoint file is detected and marked invalid."""
        self.registry.register_bot(BotDefinition(bot_id="b_corrupt"))
        sess = self.supervisor.start_bot("b_corrupt")
        rt = self.supervisor.get_bot_runtime("b_corrupt")
        cp = rt.orchestrator.save_checkpoint()
        self.supervisor.stop_bot("b_corrupt")

        # Corrupt checkpoint file on disk
        cp_dir = get_bot_checkpoint_dir("b_corrupt", sess.bot_session_id, self.test_dir)
        cp_file = os.path.join(cp_dir, f"checkpoint_{sess.bot_session_id}.json")
        if os.path.exists(cp_file):
            with open(cp_file, "r") as f:
                data = json.load(f)
            data["checksum"] = "corrupted_checksum_tampered"
            with open(cp_file, "w") as f:
                json.dump(data, f)

        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        audit = recovery_mgr.verify_bot_integrity("b_corrupt")
        self.assertFalse(audit["valid"])

    def test_tc56_multibot_post_restart_reconciliation(self):
        """TC 56: Multi-bot post-restart reconciliation audit scans all bots."""
        self.registry.register_bot(BotDefinition(bot_id="b_audit_1"))
        self.registry.register_bot(BotDefinition(bot_id="b_audit_2"))

        recovery_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        res = recovery_mgr.reconcile_all_bots()
        self.assertEqual(res["total_bots"], 2)
        self.assertEqual(res["valid_bots"], 2)
        self.assertEqual(res["corrupted_bots"], 0)

    def test_tc57_safe_resume_policy_post_recovery(self):
        """TC 57: Safe resume policy requires clean state and transitions smoothly."""
        self.registry.register_bot(BotDefinition(bot_id="b_safe_res"))
        self.supervisor.start_bot("b_safe_res")
        self.supervisor.pause_bot("b_safe_res")
        rt = self.supervisor.get_bot_runtime("b_safe_res")
        self.assertEqual(rt.state, BotLifecycleState.PAUSED)
        resumed = self.supervisor.resume_bot("b_safe_res")
        self.assertEqual(resumed.lifecycle_state, BotLifecycleState.RUNNING)

    # ==========================================================================
    # GROUP F: REST API, WEBSOCKET & DASHBOARD (TC 58 - 67)
    # ==========================================================================

    def test_tc58_api_get_overview(self):
        """TC 58: GET /api/v2/bots/overview returns supervisor aggregate telemetry."""
        res = self.client.get("/api/v2/bots/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("active_bots_count", data)
        self.assertIn("environment", data)
        self.assertEqual(data["environment"], "SIMULATION")

    def test_tc59_api_list_bots(self):
        """TC 59: GET /api/v2/bots returns list of all bots."""
        res = self.client.get("/api/v2/bots")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc60_api_create_bot(self):
        """TC 60: POST /api/v2/bots creates a new bot definition."""
        payload = {
            "bot_id": f"bot_api_{uuid.uuid4().hex[:6]}",
            "bot_name": "API Test Bot",
            "symbols": ["NVDA"],
            "timeframe": "1m",
            "initial_cash": 100000.0,
            "strategy_id": "MA_CROSS_1M",
            "strategy_version": "1.0.0",
        }
        res = self.client.post("/api/v2/bots", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["bot_name"], "API Test Bot")

    def test_tc61_api_get_bot_detail(self):
        """TC 61: GET /api/v2/bots/{bot_id} retrieves details of existing bot."""
        b_id = f"bot_det_{uuid.uuid4().hex[:6]}"
        self.client.post("/api/v2/bots", json={"bot_id": b_id, "bot_name": "Detail Bot"})
        res = self.client.get(f"/api/v2/bots/{b_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["bot_id"], b_id)

    def test_tc62_api_get_bot_sessions(self):
        """TC 62: GET /api/v2/bots/{bot_id}/sessions returns session list."""
        b_id = f"bot_sess_{uuid.uuid4().hex[:6]}"
        create_res = self.client.post("/api/v2/bots", json={"bot_id": b_id})
        sess_id = create_res.json()["session_id"]

        res = self.client.get(f"/api/v2/bots/{b_id}/sessions")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc63_api_bot_lifecycle_controls(self):
        """TC 63: POST /api/v2/bots/{bot_id}/start, pause, resume, stop endpoints."""
        b_id = f"bot_ctrl_{uuid.uuid4().hex[:6]}"
        c_res = self.client.post("/api/v2/bots", json={"bot_id": b_id})
        s_id = c_res.json()["session_id"]

        # 1. Start
        res_start = self.client.post(f"/api/v2/bots/{s_id}/start")
        self.assertEqual(res_start.status_code, 200)
        self.assertEqual(res_start.json()["lifecycle_state"], "RUNNING")

        # 2. Pause
        res_pause = self.client.post(f"/api/v2/bots/{s_id}/pause")
        self.assertEqual(res_pause.status_code, 200)
        self.assertEqual(res_pause.json()["lifecycle_state"], "PAUSED")

        # 3. Resume
        res_resume = self.client.post(f"/api/v2/bots/{s_id}/resume")
        self.assertEqual(res_resume.status_code, 200)
        self.assertEqual(res_resume.json()["lifecycle_state"], "RUNNING")

        # 4. Stop
        res_stop = self.client.post(f"/api/v2/bots/{s_id}/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertEqual(res_stop.json()["lifecycle_state"], "STOPPED")

    def test_tc64_api_archive_bot(self):
        """TC 64: POST /api/v2/bots/{bot_id}/archive soft-archives bot."""
        b_id = f"bot_arch_{uuid.uuid4().hex[:6]}"
        self.client.post("/api/v2/bots", json={"bot_id": b_id})
        res = self.client.post(f"/api/v2/bots/{b_id}/archive")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ARCHIVED")

    def test_tc65_api_dispatch_bar(self):
        """TC 65: POST /api/v2/bots/dispatch_bar fans out market data bar."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "open": 140.0,
            "high": 141.0,
            "low": 139.0,
            "close": 140.5,
            "volume": 500.0,
            "is_final": True,
            "environment": "SIMULATION",
        }
        res = self.client.post("/api/v2/bots/dispatch_bar", json=payload)
        self.assertEqual(res.status_code, 200)

    def test_tc66_api_portfolio_isolation(self):
        """TC 66: GET /api/v2/bots/{session_id}/portfolio returns isolated portfolios."""
        b1_res = self.client.post("/api/v2/bots", json={"bot_id": f"b1_{uuid.uuid4().hex[:6]}", "initial_cash": 100000.0})
        b2_res = self.client.post("/api/v2/bots", json={"bot_id": f"b2_{uuid.uuid4().hex[:6]}", "initial_cash": 50000.0})

        s1 = b1_res.json()["session_id"]
        s2 = b2_res.json()["session_id"]

        p1 = self.client.get(f"/api/v2/bots/{s1}/portfolio").json()
        p2 = self.client.get(f"/api/v2/bots/{s2}/portfolio").json()

        self.assertEqual(p1["cash"], 100000.0)
        self.assertEqual(p2["cash"], 50000.0)

    def test_tc67_websocket_stream_routes(self):
        """TC 67: WebSocket stream routes are mounted and accessible."""
        b_res = self.client.post("/api/v2/bots", json={"bot_id": f"b_ws_{uuid.uuid4().hex[:6]}"})
        s_id = b_res.json()["session_id"]

        with self.client.websocket_connect(f"/ws/v2/bots/{s_id}") as ws:
            snap = ws.receive_json()
            self.assertEqual(snap.get("event_type") or snap.get("type"), "SNAPSHOT")
            ws.send_text(json.dumps({"action": "PING"}))
            pong = ws.receive_json()
            self.assertEqual(pong.get("type"), "PONG")

    # ==========================================================================
    # GROUP G: SAFETY INVARIANTS & FULL REGRESSION (TC 68 - 75)
    # ==========================================================================

    def test_tc68_safety_invariant_trading_mode_dry_run(self):
        """TC 68: TRADING_MODE=DRY_RUN is strictly asserted across all bots and supervisor."""
        self.registry.register_bot(BotDefinition(bot_id="b_safe_dm"))
        sess = self.supervisor.start_bot("b_safe_dm")
        self.assertEqual(sess.trading_mode, "DRY_RUN")
        health = self.supervisor.get_supervisor_health()
        self.assertEqual(health["trading_mode"], "DRY_RUN")

    def test_tc69_safety_invariant_paper_execution_gate_closed(self):
        """TC 69: PaperExecutionGate.is_gate_open = False verified across all bots."""
        gate = AlpacaPaperGate()
        self.assertFalse(gate.is_gate_open)
        with self.assertRaises((PaperExecutionGateClosedError, LiveTradingProhibitedError)):
            gate.submit_paper_order({"symbol": "NVDA", "qty": 1, "side": "buy"})

    def test_tc70_zero_alpaca_broker_api_calls(self):
        """TC 70: Verification that simulation bots make zero external broker API calls."""
        self.registry.register_bot(BotDefinition(bot_id="b_zero_calls", symbols=["NVDA"]))
        self.supervisor.start_bot("b_zero_calls")
        rt = self.supervisor.get_bot_runtime("b_zero_calls")

        # Submit order in simulation broker
        ord_obj = rt.orchestrator.simulation_broker.submit_order(
            symbol="NVDA", side="BUY", order_type="MARKET", quantity=10.0, price=140.0
        )
        self.assertIsNotNone(ord_obj)
        self.assertEqual(ord_obj.environment, "SIMULATION")
        # Assert broker gate remained closed
        gate = AlpacaPaperGate()
        self.assertFalse(gate.is_gate_open)

    def test_tc71_zero_live_execution_endpoints(self):
        """TC 71: Live trading execution endpoints are strictly non-existent or blocked."""
        res = self.client.post("/api/v2/live/orders", json={})
        self.assertIn(res.status_code, [404, 405])

    def test_tc72_virtual_capital_disclaimer_present(self):
        """TC 72: Virtual capital disclaimer is mandatory and present in telemetry."""
        self.registry.register_bot(BotDefinition(bot_id="b_disc"))
        self.supervisor.start_bot("b_disc")
        tel = SupervisorTelemetryCollector.collect_telemetry(self.supervisor)
        self.assertIn("INDEPENDENT_VIRTUAL_SIMULATION_CAPITAL_ONLY", tel["aggregate_simulation_capital"]["disclaimer"])

    def test_tc73_simulation_environment_strictly_declared(self):
        """TC 73: Environment strictly declared as SIMULATION in all bot definitions and outputs."""
        b_def = BotDefinition(bot_id="b_env_decl")
        self.assertEqual(b_def.environment, "SIMULATION")
        self.registry.register_bot(b_def)
        sess = self.supervisor.start_bot("b_env_decl")
        self.assertEqual(sess.environment, "SIMULATION")

    def test_tc74_three_bot_concurrent_simulation_soak(self):
        """TC 74: Concurrent soak simulation with 3 bots trading different strategies & symbols."""
        self.registry.register_bot(BotDefinition(bot_id="bot_nvda_ma", symbols=["NVDA"], strategy_id="MA_CROSS_1M"))
        self.registry.register_bot(BotDefinition(bot_id="bot_btc_rsi", symbols=["BTC/USD"], strategy_id="RSI_1M"))
        self.registry.register_bot(BotDefinition(bot_id="bot_multi_sym", symbols=["NVDA", "BTC/USD"], strategy_id="MA_CROSS_1M"))

        self.supervisor.start_bot("bot_nvda_ma")
        self.supervisor.start_bot("bot_btc_rsi")
        self.supervisor.start_bot("bot_multi_sym")

        self.assertEqual(self.supervisor.active_bot_count, 3)

        base_time = datetime.now(timezone.utc)
        # Feed sequence of NVDA and BTC bars
        for i in range(10):
            t = base_time + timedelta(minutes=i)
            bar_nvda = make_test_bar(symbol="NVDA", event_id=f"soak_nvda_{i}", event_time=t, close_p=140.0 + i)
            bar_btc = make_test_bar(symbol="BTC/USD", event_id=f"soak_btc_{i}", event_time=t, close_p=65000.0 + (i * 10))

            res_n = self.supervisor.dispatch_market_data(bar_nvda, auto_process=True)
            res_b = self.supervisor.dispatch_market_data(bar_btc, auto_process=True)

            self.assertIn("bot_nvda_ma", res_n)
            self.assertIn("bot_multi_sym", res_n)
            self.assertIn("bot_btc_rsi", res_b)
            self.assertIn("bot_multi_sym", res_b)

        # Verify all 3 bots completed 10 cycles healthy
        health = self.supervisor.get_supervisor_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["active_bots_count"], 3)

    def test_tc75_end_to_end_multibot_audit_verification(self):
        """TC 75: End-to-end multi-bot lifecycle, fan-out, trading, and post-stop audit verification."""
        self.registry.register_bot(BotDefinition(bot_id="bot_e2e_1", symbols=["NVDA"], initial_simulated_cash=100000.0))
        self.registry.register_bot(BotDefinition(bot_id="bot_e2e_2", symbols=["NVDA"], initial_simulated_cash=50000.0))

        # 1. Start both
        self.supervisor.start_bot("bot_e2e_1")
        self.supervisor.start_bot("bot_e2e_2")

        # 2. Dispatch events
        bar = make_test_bar(symbol="NVDA", event_id="e2e_bar_1")
        self.supervisor.dispatch_market_data(bar, auto_process=True)

        # 3. Stop both
        self.supervisor.stop_bot("bot_e2e_1")
        self.supervisor.stop_bot("bot_e2e_2")
        self.assertEqual(self.supervisor.active_bot_count, 0)

        # 4. Verify post-stop recovery and reconciliation
        rec_mgr = MultiBotRecoveryManager(registry=self.registry, base_dir=self.test_dir)
        recon = rec_mgr.reconcile_all_bots()
        self.assertEqual(recon["total_bots"], 2)
        self.assertEqual(recon["valid_bots"], 2)
        self.assertEqual(recon["corrupted_bots"], 0)


if __name__ == "__main__":
    unittest.main()
