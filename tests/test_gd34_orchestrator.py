"""
tests/test_gd34_orchestrator.py — GĐ34 Bot Core Orchestrator & Lifecycle Controller Test Suite
Contains 65 automated unit, integration, recovery, and safety tests covering:
Group A: Lifecycle State Machine (TC 01 - 10)
Group B: Orchestrator Integration & Configuration (TC 11 - 18)
Group C: Event Loop & Queue Backpressure (TC 19 - 27)
Group D: Pause & Resume Semantics (TC 28 - 34)
Group E: Graceful Stop & Stop Policies (TC 35 - 41)
Group F: Failure, Checkpoints & Recovery (TC 42 - 49)
Group G: Performance & Health Monitoring (TC 50 - 56)
Group H: Safety Invariants & Sandbox Isolation (TC 57 - 65)
"""

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import os
import shutil
import json
import uuid

from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    SimulatedPosition,
)
from libs.bot.orchestration.lifecycle import (
    BotLifecycleState,
    TERMINAL_STATES,
    ACTIVE_STATES,
    InvalidLifecycleStateTransitionError,
    BotLifecycleStateMachine,
)
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.event_journal import BotEventJournal
from libs.bot.orchestration.checkpoint import (
    BotCheckpoint,
    BotCheckpointManager,
)
from libs.bot.orchestration.health import BotHealthMonitor
from libs.bot.orchestration.performance import BotPerformanceReporter
from libs.bot.orchestration.recovery import BotRecoveryManager
from libs.bot.orchestration.event_loop import (
    QueueOverflowError,
    BotEventLoop,
)
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.command_service import BotCommandService

from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.strategies.base import BaseStrategy
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.bot.execution.order_manager import SimulationOrderManager
from libs.bot.execution.lifecycle import OrderState
from libs.alpaca_paper_gate import AlpacaPaperGate


class MockTestStrategy(BaseStrategy):
    """Deterministic strategy for testing event loop and signals."""

    def __init__(
        self,
        strategy_id: str = "mock_test_strat",
        signal_on_bar: int = 2,
        signal_type: str = "BUY",
        symbol: str = "NVDA",
    ):
        super().__init__(
            strategy_id=strategy_id,
            strategy_name="MockTestStrategy",
            strategy_version="1.0.0",
        )
        self.signal_on_bar = signal_on_bar
        self.signal_type = signal_type
        self.target_symbol = symbol
        self.bar_count = 0

    @property
    def configuration_schema(self):
        return {}

    @property
    def required_indicators(self):
        return []

    def reset_state(self, symbol=None):
        self.bar_count = 0

    def generate_signals(self, market_data: MarketDataEvent) -> StrategySignal:
        self.bar_count += 1
        sig_type = self.signal_type if self.bar_count == self.signal_on_bar else "HOLD"
        return StrategySignal(
            signal_id=f"sig_{market_data.bar_key}_{self.bar_count}",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            signal_type=sig_type,
            price=market_data.close,
            strength=0.90 if sig_type != "HOLD" else 0.50,
            source_bar_key=market_data.bar_key,
            signal_time=market_data.event_time,
            environment="SIMULATION",
        )


class TestGD34Orchestrator(unittest.TestCase):
    """GĐ34 Complete Orchestrator & Lifecycle Controller Test Suite."""

    def setUp(self):
        self.test_dir = "data/paper_bot/test_gd34_data"
        self.session_dir = os.path.join(self.test_dir, "sessions")
        self.checkpoint_dir = os.path.join(self.test_dir, "checkpoints")
        self.performance_dir = os.path.join(self.test_dir, "performance")
        self.journal_dir = os.path.join(self.test_dir, "journal")

        os.makedirs(self.session_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.performance_dir, exist_ok=True)
        os.makedirs(self.journal_dir, exist_ok=True)

        self.session_store = SessionStore(storage_dir=self.session_dir)
        self.checkpoint_manager = BotCheckpointManager(storage_dir=self.checkpoint_dir)

        # Setup standard bot components
        self.session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        self.risk_config = RiskConfig(
            max_position_qty=100.0,
            max_position_notional=25000.0,
            max_drawdown_pct=0.15,
            sizing_mode="FIXED_QTY",
            fixed_qty=10.0,
        )
        self.session = BotSession(
            session_id=self.session_id,
            bot_session_id=self.session_id,
            bot_id="test_bot_01",
            bot_name="TestPaperBot",
            strategy_name="mock_test_strat",
            strategy_id="mock_test_strat",
            strategy_version="1.0.0",
            symbols=["NVDA"],
            timeframe="1m",
            initial_cash=100000.0,
            risk_config_hash=self.risk_config.compute_hash(),
            status=BotLifecycleState.STOPPED,
            lifecycle_state=BotLifecycleState.STOPPED,
            environment="SIMULATION",
            trading_mode="DRY_RUN",
        )

        self.portfolio = SimulationPortfolioManager(
            portfolio_id=self.session_id,
            bot_session_id=self.session_id,
            initial_cash=100000.0,
        )
        self.strategy_engine = StrategyExecutionEngine()
        self.mock_strategy = MockTestStrategy(strategy_id="mock_test_strat", signal_on_bar=2, symbol="NVDA")
        self.strategy_engine.add_strategy_instance(self.mock_strategy, ["NVDA"])

        self.simulation_broker = SimulationBroker(
            portfolio=self.portfolio,
            max_participation_rate=0.20,
        )

        self.orchestrator = BotOrchestrator(
            session=self.session,
            portfolio=self.portfolio,
            risk_config=self.risk_config,
            strategy_engine=self.strategy_engine,
            simulation_broker=self.simulation_broker,
            session_store=self.session_store,
            checkpoint_manager=self.checkpoint_manager,
            stop_policy=StopPolicy.CANCEL_REMAINDER,
            max_queue_size=10,
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_bar(
        self,
        symbol: str = "NVDA",
        minute_offset: int = 0,
        price: float = 140.0,
        volume: float = 5000.0,
        is_final: bool = True,
        environment: str = "SIMULATION",
    ) -> MarketDataEvent:
        now = datetime.now(timezone.utc)
        dt = now - timedelta(seconds=120 - (minute_offset * 10))
        return MarketDataEvent(
            event_id=f"evt_{symbol}_{minute_offset}_{uuid.uuid4().hex[:6]}",
            symbol=symbol,
            timeframe="1m",
            event_time=dt,
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price + 0.5,
            volume=volume,
            vwap=price + 0.2,
            is_final=is_final,
            environment=environment,
        )

    # =========================================================================
    # Group A: Lifecycle State Machine (TC 01 - 10)
    # =========================================================================

    def test_01_valid_transition_starting_to_running(self):
        """TC-01: Verifies valid transition STARTING -> RUNNING."""
        session = BotSession(lifecycle_state=BotLifecycleState.STARTING)
        res = BotLifecycleStateMachine.transition(session, BotLifecycleState.RUNNING, reason="Init complete")
        self.assertTrue(res)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)
        self.assertEqual(session.status, BotLifecycleState.RUNNING)
        self.assertIsNotNone(session.started_at)

    def test_02_valid_transition_running_to_paused(self):
        """TC-02: Verifies valid transition RUNNING -> PAUSED."""
        session = BotSession(lifecycle_state=BotLifecycleState.RUNNING)
        res = BotLifecycleStateMachine.transition(session, BotLifecycleState.PAUSED, reason="User requested pause")
        self.assertTrue(res)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.PAUSED)
        self.assertEqual(session.status, BotLifecycleState.PAUSED)
        self.assertIsNotNone(session.paused_at)

    def test_03_valid_transition_paused_to_running(self):
        """TC-03: Verifies valid transition PAUSED -> RUNNING."""
        session = BotSession(lifecycle_state=BotLifecycleState.PAUSED)
        res = BotLifecycleStateMachine.transition(session, BotLifecycleState.RUNNING, reason="User resumed")
        self.assertTrue(res)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)

    def test_04_valid_transition_running_to_stopping_to_stopped(self):
        """TC-04: Verifies normal shutdown path RUNNING -> STOPPING -> STOPPED."""
        session = BotSession(lifecycle_state=BotLifecycleState.RUNNING)
        res1 = BotLifecycleStateMachine.transition(session, BotLifecycleState.STOPPING, reason="Shutting down")
        self.assertTrue(res1)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.STOPPING)

        res2 = BotLifecycleStateMachine.transition(session, BotLifecycleState.STOPPED, reason="Cleanup complete")
        self.assertTrue(res2)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.STOPPED)
        self.assertEqual(session.status, BotLifecycleState.STOPPED)
        self.assertIsNotNone(session.stopped_at)

    def test_05_valid_transition_paused_to_stopping_to_stopped(self):
        """TC-05: Verifies shutdown from PAUSED -> STOPPING -> STOPPED."""
        session = BotSession(lifecycle_state=BotLifecycleState.PAUSED)
        res1 = BotLifecycleStateMachine.transition(session, BotLifecycleState.STOPPING, reason="Operator stop")
        self.assertTrue(res1)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.STOPPING)

        res2 = BotLifecycleStateMachine.transition(session, BotLifecycleState.STOPPED, reason="Finished")
        self.assertTrue(res2)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.STOPPED)

    def test_06_transition_any_active_to_error(self):
        """TC-06: Verifies transitions from RUNNING or PAUSED to ERROR state with context."""
        session = BotSession(lifecycle_state=BotLifecycleState.RUNNING)
        res = BotLifecycleStateMachine.transition(
            session,
            BotLifecycleState.ERROR,
            reason="Fatal feed error",
            error_code="FEED_DISCONNECTED",
            error_message="Redpanda broker unreachable",
        )
        self.assertTrue(res)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.ERROR)
        self.assertEqual(session.error_code, "FEED_DISCONNECTED")
        self.assertEqual(session.error_message, "Redpanda broker unreachable")

    def test_07_invalid_transition_stopped_to_running_rejected(self):
        """TC-07: Transitioning STOPPED -> RUNNING directly raises InvalidLifecycleStateTransitionError."""
        session = BotSession(lifecycle_state=BotLifecycleState.STOPPED)
        with self.assertRaises(InvalidLifecycleStateTransitionError):
            BotLifecycleStateMachine.transition(session, BotLifecycleState.RUNNING)

    def test_08_invalid_transition_paused_to_starting_rejected(self):
        """TC-08: Attempting PAUSED -> STARTING is rejected as illegal transition."""
        session = BotSession(lifecycle_state=BotLifecycleState.PAUSED)
        with self.assertRaises(InvalidLifecycleStateTransitionError):
            BotLifecycleStateMachine.transition(session, BotLifecycleState.STARTING)

    def test_09_terminal_state_stopped_cannot_transition(self):
        """TC-09: Terminal state STOPPED cannot transition directly to PAUSED or ERROR."""
        session = BotSession(lifecycle_state=BotLifecycleState.STOPPED)
        with self.assertRaises(InvalidLifecycleStateTransitionError):
            BotLifecycleStateMachine.transition(session, BotLifecycleState.PAUSED)

    def test_10_idempotent_transition(self):
        """TC-10: Self-transition (e.g. RUNNING -> RUNNING) is idempotent and returns True."""
        session = BotSession(lifecycle_state=BotLifecycleState.RUNNING)
        res = BotLifecycleStateMachine.transition(session, BotLifecycleState.RUNNING, reason="No-op check")
        self.assertTrue(res)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)

    # =========================================================================
    # Group B: Orchestrator Integration & Configuration (TC 11 - 18)
    # =========================================================================

    def test_11_orchestrator_initialization(self):
        """TC-11: Orchestrator initializes with all subsystems correctly bound."""
        self.assertIsNotNone(self.orchestrator.session)
        self.assertIsNotNone(self.orchestrator.portfolio)
        self.assertIsNotNone(self.orchestrator.risk_config)
        self.assertIsNotNone(self.orchestrator.strategy_engine)
        self.assertIsNotNone(self.orchestrator.simulation_broker)
        self.assertIsNotNone(self.orchestrator.event_loop)
        self.assertIsNotNone(self.orchestrator.health_monitor)
        self.assertIsNotNone(self.orchestrator.performance_reporter)

    def test_12_config_hash_computation(self):
        """TC-12: Orchestrator binds deterministic SHA-256 risk_config_hash."""
        expected_hash = self.risk_config.compute_hash()
        self.assertEqual(self.orchestrator.session.risk_config_hash, expected_hash)
        self.assertTrue(len(expected_hash) > 0)

    def test_13_initial_session_persisted(self):
        """TC-13: Session is written to SessionStore upon initialization."""
        loaded = self.session_store.get_session(self.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.bot_session_id, self.session_id)
        self.assertEqual(loaded.lifecycle_state, BotLifecycleState.STOPPED)

    def test_14_orchestrator_start_activates_loop(self):
        """TC-14: start() transitions state to RUNNING and unpauses event loop."""
        res = self.orchestrator.start()
        self.assertTrue(res)
        self.assertEqual(self.orchestrator.state, BotLifecycleState.RUNNING)
        self.assertFalse(self.orchestrator.event_loop.is_paused)

    def test_15_start_from_stopped_succeeds(self):
        """TC-15: Bot starting from initial STOPPED transitions smoothly to RUNNING."""
        self.assertEqual(self.orchestrator.session.lifecycle_state, BotLifecycleState.STOPPED)
        started = self.orchestrator.start()
        self.assertTrue(started)
        self.assertEqual(self.orchestrator.session.lifecycle_state, BotLifecycleState.RUNNING)

    def test_16_state_property(self):
        """TC-16: state property returns the current lifecycle state."""
        self.assertEqual(self.orchestrator.state, BotLifecycleState.STOPPED)
        self.orchestrator.start()
        self.assertEqual(self.orchestrator.state, BotLifecycleState.RUNNING)

    def test_17_session_store_atomic_retrieval(self):
        """TC-17: Reading session from SessionStore matches current orchestrator state."""
        self.orchestrator.start()
        loaded = self.session_store.get_session(self.session_id)
        self.assertEqual(loaded.lifecycle_state, BotLifecycleState.RUNNING)

    def test_18_command_service_create_bot(self):
        """TC-18: BotCommandService factory creates and registers orchestrator with defaults."""
        cmd_svc = BotCommandService(session_store=self.session_store)
        orch = cmd_svc.create_bot(
            bot_id="bot_auto_01",
            bot_name="AutoBot",
            symbols=["NVDA"],
            initial_cash=50000.0,
        )
        self.assertIsNotNone(orch)
        self.assertEqual(orch.portfolio.cash, Decimal("50000.00"))
        self.assertIn(orch.session.bot_session_id, cmd_svc._active_orchestrators)

    # =========================================================================
    # Group C: Event Loop & Queue Backpressure (TC 19 - 27)
    # =========================================================================

    def test_19_enqueue_valid_event(self):
        """TC-19: Enqueuing valid 1m SIMULATION finalized bar succeeds."""
        bar = self._create_bar(minute_offset=1)
        enqueued = self.orchestrator.event_loop.enqueue_event(bar)
        self.assertTrue(enqueued)
        self.assertEqual(len(self.orchestrator.event_loop._queue), 1)
        self.assertEqual(self.orchestrator.health_monitor.queue_depth, 1)

    def test_20_reject_non_simulation_event(self):
        """TC-20: Event not tagged SIMULATION raises ValueError on enqueue."""
        bar = self._create_bar(minute_offset=1, environment="LIVE")
        with self.assertRaises(ValueError):
            self.orchestrator.event_loop.enqueue_event(bar)

    def test_21_reject_provisional_unfinalized_bar(self):
        """TC-21: Bar with is_final=False is rejected from queue."""
        bar = self._create_bar(minute_offset=1, is_final=False)
        enqueued = self.orchestrator.event_loop.enqueue_event(bar)
        self.assertFalse(enqueued)
        self.assertEqual(len(self.orchestrator.event_loop._queue), 0)

    def test_22_backpressure_queue_overflow(self):
        """TC-22: Exceeding max_queue_size raises QueueOverflowError."""
        # Max queue size configured to 10 in setUp
        for i in range(10):
            bar = self._create_bar(minute_offset=i)
            self.orchestrator.event_loop.enqueue_event(bar)

        overflow_bar = self._create_bar(minute_offset=11)
        with self.assertRaises(QueueOverflowError):
            self.orchestrator.event_loop.enqueue_event(overflow_bar)

    def test_23_process_next_event_drains_one(self):
        """TC-23: process_next_event() pops exactly one event and decrements depth."""
        bar1 = self._create_bar(minute_offset=1)
        bar2 = self._create_bar(minute_offset=2)
        self.orchestrator.event_loop.enqueue_event(bar1)
        self.orchestrator.event_loop.enqueue_event(bar2)

        res = self.orchestrator.event_loop.process_next_event()
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "PROCESSED")
        self.assertEqual(len(self.orchestrator.event_loop._queue), 1)
        self.assertEqual(self.orchestrator.health_monitor.queue_depth, 1)

    def test_24_drain_queue_processes_all(self):
        """TC-24: drain_queue() processes all queued events to 0 depth."""
        for i in range(4):
            self.orchestrator.event_loop.enqueue_event(self._create_bar(minute_offset=i))

        count = self.orchestrator.event_loop.drain_queue()
        self.assertEqual(count, 4)
        self.assertEqual(len(self.orchestrator.event_loop._queue), 0)

    def test_25_deduplication_via_journal(self):
        """TC-25: Submitting identical bar twice returns SKIPPED_DUPLICATE on second pass."""
        bar = self._create_bar(minute_offset=1)
        self.orchestrator.event_loop.enqueue_event(bar)
        res1 = self.orchestrator.event_loop.process_next_event()
        self.assertEqual(res1["status"], "PROCESSED")

        # Enqueue identical bar
        self.orchestrator.event_loop.enqueue_event(bar)
        res2 = self.orchestrator.event_loop.process_next_event()
        self.assertEqual(res2["status"], "SKIPPED_DUPLICATE")

    def test_26_anti_lookahead_execution_order(self):
        """TC-26: Prior working order is filled on current bar BEFORE current bar generates signal."""
        # Submit a working order manually into simulation broker
        intent = SimulationOrderIntent(
            intent_id="intent_prior_01",
            decision_id="dec_01",
            signal_id="sig_01",
            bot_session_id=self.session_id,
            portfolio_id=self.session_id,
            symbol="NVDA",
            side="BUY",
            order_type="MARKET",
            proposed_quantity=10.0,
            proposed_notional=1400.0,
            reference_price=140.0,
            risk_configuration_version="1.0.0",
            idempotency_key="idemp_prior_01",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        order = self.simulation_broker.submit_intent(intent)
        order.source_bar_key = "NVDA:1m:prior_bar"

        # Now submit bar through orchestrator event loop
        bar = self._create_bar(minute_offset=1, price=142.0)
        self.orchestrator.start()
        res = self.orchestrator.submit_bar(bar, auto_process=True)

        self.assertIsNotNone(res)
        self.assertEqual(res["fills_generated"], 1)
        self.assertEqual(order.status, OrderState.FILLED)
        # Position opened
        pos = self.portfolio.positions.get_position("NVDA")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.qty, 10.0)

    def test_27_end_to_end_signal_to_order_intent(self):
        """TC-27: Bar 2 triggers MockStrategy BUY signal -> SignalDecision ACCEPTED -> Order WORKING."""
        self.orchestrator.start()
        # Bar 1 -> HOLD
        b1 = self._create_bar(minute_offset=1, price=140.0)
        res1 = self.orchestrator.submit_bar(b1, auto_process=True)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 0)

        # Bar 2 -> BUY signal triggered
        b2 = self._create_bar(minute_offset=2, price=141.0)
        res2 = self.orchestrator.submit_bar(b2, auto_process=True)
        self.assertIsNotNone(res2["signal"])
        self.assertEqual(res2["signal"].signal_type, "BUY")
        self.assertIsNotNone(res2["decision"])
        self.assertEqual(res2["decision"].status, "ACCEPTED")
        self.assertIsNotNone(res2["intent"])

        # Order should now be in WORKING state awaiting next bar
        open_orders = self.simulation_broker.order_manager.get_open_orders()
        self.assertEqual(len(open_orders), 1)
        self.assertEqual(open_orders[0].status, OrderState.WORKING)

    # =========================================================================
    # Group D: Pause & Resume Semantics (TC 28 - 34)
    # =========================================================================

    def test_28_pause_orchestrator(self):
        """TC-28: Calling pause() transitions state to PAUSED and stops event loop."""
        self.orchestrator.start()
        res = self.orchestrator.pause(reason="Maintenance")
        self.assertTrue(res)
        self.assertEqual(self.orchestrator.state, BotLifecycleState.PAUSED)
        self.assertTrue(self.orchestrator.event_loop.is_paused)

    def test_29_submit_bar_while_paused_rejected(self):
        """TC-29: submit_bar returns None when orchestrator is in PAUSED state."""
        self.orchestrator.start()
        self.orchestrator.pause()
        bar = self._create_bar(minute_offset=1)
        res = self.orchestrator.submit_bar(bar)
        self.assertIsNone(res)

    def test_30_pause_does_not_cancel_working_orders(self):
        """TC-30: Pausing bot leaves active simulation orders intact."""
        self.orchestrator.start()
        intent = SimulationOrderIntent(
            intent_id="intent_hold_01",
            decision_id="dec_02",
            signal_id="sig_02",
            bot_session_id=self.session_id,
            portfolio_id=self.session_id,
            symbol="NVDA",
            side="BUY",
            order_type="LIMIT",
            limit_price=135.0,
            proposed_quantity=5.0,
            proposed_notional=675.0,
            reference_price=140.0,
            risk_configuration_version="1.0.0",
            idempotency_key="idemp_hold_01",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        order = self.simulation_broker.submit_intent(intent)
        self.assertEqual(order.status, OrderState.WORKING)

        self.orchestrator.pause()
        self.assertEqual(order.status, OrderState.WORKING)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 1)

    def test_31_resume_orchestrator(self):
        """TC-31: resume() transitions from PAUSED to RUNNING and unpauses event loop."""
        self.orchestrator.start()
        self.orchestrator.pause()
        res = self.orchestrator.resume()
        self.assertTrue(res)
        self.assertEqual(self.orchestrator.state, BotLifecycleState.RUNNING)
        self.assertFalse(self.orchestrator.event_loop.is_paused)

    def test_32_processing_resumes_after_resume(self):
        """TC-32: Events submitted after resume are processed normally."""
        self.orchestrator.start()
        self.orchestrator.pause()
        self.orchestrator.resume()

        bar = self._create_bar(minute_offset=1)
        res = self.orchestrator.submit_bar(bar, auto_process=True)
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "PROCESSED")

    def test_33_pause_creates_checkpoint(self):
        """TC-33: Automatic checkpoint is created and persisted on pause."""
        self.orchestrator.start()
        self.orchestrator.pause()
        cp = self.checkpoint_manager.load_checkpoint(self.session_id)
        self.assertIsNotNone(cp)
        self.assertEqual(cp.bot_session_id, self.session_id)

    def test_34_command_service_pause_and_resume(self):
        """TC-34: BotCommandService pause_bot and resume_bot work end-to-end."""
        cmd_svc = BotCommandService(session_store=self.session_store)
        orch = cmd_svc.create_bot(bot_id="b_pause_test", initial_cash=20000.0)
        s_id = orch.session.bot_session_id

        cmd_svc.start_bot(s_id)
        self.assertEqual(orch.state, BotLifecycleState.RUNNING)

        cmd_svc.pause_bot(s_id)
        self.assertEqual(orch.state, BotLifecycleState.PAUSED)

        cmd_svc.resume_bot(s_id)
        self.assertEqual(orch.state, BotLifecycleState.RUNNING)

    # =========================================================================
    # Group E: Graceful Stop & Stop Policies (TC 35 - 41)
    # =========================================================================

    def test_35_stop_cancel_remainder_cancels_working_orders(self):
        """TC-35: Stop with CANCEL_REMAINDER cancels all open orders in broker."""
        self.orchestrator.start()
        intent = SimulationOrderIntent(
            intent_id="intent_cancel_01",
            decision_id="dec_03",
            signal_id="sig_03",
            bot_session_id=self.session_id,
            portfolio_id=self.session_id,
            symbol="NVDA",
            side="BUY",
            order_type="LIMIT",
            limit_price=130.0,
            proposed_quantity=10.0,
            proposed_notional=1300.0,
            reference_price=140.0,
            risk_configuration_version="1.0.0",
            idempotency_key="idemp_cancel_01",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        order = self.simulation_broker.submit_intent(intent)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 1)

        self.orchestrator.stop(policy=StopPolicy.CANCEL_REMAINDER)
        self.assertEqual(order.status, OrderState.CANCELLED)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 0)

    def test_36_stop_cancels_remainder_releases_cash_reservation(self):
        """TC-36: Order cancellation during shutdown unlocks reserved cash."""
        self.orchestrator.start()
        intent = SimulationOrderIntent(
            intent_id="intent_cancel_02",
            decision_id="dec_04",
            signal_id="sig_04",
            bot_session_id=self.session_id,
            portfolio_id=self.session_id,
            symbol="NVDA",
            side="BUY",
            order_type="LIMIT",
            limit_price=130.0,
            proposed_quantity=10.0,
            proposed_notional=1300.0,
            reference_price=140.0,
            risk_configuration_version="1.0.0",
            idempotency_key="idemp_cancel_02",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        self.simulation_broker.submit_intent(intent)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("1400.00"))

        self.orchestrator.stop(policy=StopPolicy.CANCEL_REMAINDER)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("0.00"))

    def test_37_stop_keep_working_policy(self):
        """TC-37: Stop with KEEP_WORKING policy leaves open orders working."""
        self.orchestrator.start()
        intent = SimulationOrderIntent(
            intent_id="intent_keep_01",
            decision_id="dec_05",
            signal_id="sig_05",
            bot_session_id=self.session_id,
            portfolio_id=self.session_id,
            symbol="NVDA",
            side="BUY",
            order_type="LIMIT",
            limit_price=130.0,
            proposed_quantity=5.0,
            proposed_notional=650.0,
            reference_price=140.0,
            risk_configuration_version="1.0.0",
            idempotency_key="idemp_keep_01",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        order = self.simulation_broker.submit_intent(intent)
        self.orchestrator.stop(policy=StopPolicy.KEEP_WORKING)
        self.assertEqual(order.status, OrderState.WORKING)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 1)

    def test_38_stop_lifecycle_transitions(self):
        """TC-38: Stop executes graceful shutdown sequence STOPPING -> STOPPED."""
        self.orchestrator.start()
        res = self.orchestrator.stop()
        self.assertTrue(res)
        self.assertEqual(self.orchestrator.state, BotLifecycleState.STOPPED)

    def test_39_stop_saves_final_checkpoint(self):
        """TC-39: Stop generates and persists final session checkpoint."""
        self.orchestrator.start()
        self.orchestrator.stop()
        cp = self.checkpoint_manager.load_checkpoint(self.session_id)
        self.assertIsNotNone(cp)
        self.assertEqual(cp.bot_session_id, self.session_id)

    def test_40_stop_generates_performance_report(self):
        """TC-40: Stop compiles and persists final performance report to disk."""
        self.orchestrator.start()
        self.orchestrator.stop()
        report_file = os.path.join(
            self.orchestrator.performance_reporter.storage_dir,
            f"perf_{self.session_id}.json",
        )
        self.assertTrue(os.path.exists(report_file))

    def test_41_command_service_stop_deregisters_bot(self):
        """TC-41: CommandService stop_bot removes orchestrator from active registry."""
        cmd_svc = BotCommandService(session_store=self.session_store)
        orch = cmd_svc.create_bot(bot_id="b_stop_test", initial_cash=10000.0)
        s_id = orch.session.bot_session_id

        cmd_svc.start_bot(s_id)
        cmd_svc.stop_bot(s_id)
        self.assertIsNone(cmd_svc.get_orchestrator(s_id))

    # =========================================================================
    # Group F: Failure, Checkpoints & Recovery (TC 42 - 49)
    # =========================================================================

    def test_42_handle_error_transitions_to_error(self):
        """TC-42: handle_error transitions to ERROR and records diagnostic context."""
        self.orchestrator.start()
        self.orchestrator.handle_error("FEED_TIMEOUT", "No data for 5 minutes")
        self.assertEqual(self.orchestrator.state, BotLifecycleState.ERROR)
        self.assertEqual(self.orchestrator.session.error_code, "FEED_TIMEOUT")
        self.assertEqual(self.orchestrator.session.error_message, "No data for 5 minutes")
        self.assertTrue(self.orchestrator.event_loop.is_paused)

    def test_43_checkpoint_integrity_sha256(self):
        """TC-43: Checkpoint contains non-empty SHA-256 checksum."""
        self.orchestrator.start()
        cp = self.orchestrator.save_checkpoint()
        self.assertIsNotNone(cp.checksum)
        self.assertEqual(len(cp.checksum), 64)

    def test_44_checkpoint_verification_valid(self):
        """TC-44: load_checkpoint successfully verifies integrity of valid checkpoint."""
        self.orchestrator.start()
        cp = self.orchestrator.save_checkpoint()
        loaded = self.checkpoint_manager.load_checkpoint(self.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.checkpoint_id, cp.checkpoint_id)
        self.assertEqual(loaded.checksum, cp.checksum)

    def test_45_checkpoint_verification_tampered_fails(self):
        """TC-45: Tampered checkpoint payload causes load_checkpoint to raise ValueError."""
        self.orchestrator.start()
        self.orchestrator.save_checkpoint()

        # Tamper checkpoint file
        cp_path = self.checkpoint_manager._get_path(self.session_id)
        with open(cp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["last_processed_bar_key"] = "TAMPERED_KEY:1m"
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with self.assertRaises(ValueError):
            self.checkpoint_manager.load_checkpoint(self.session_id)

    def test_46_recovery_manager_successful_recovery(self):
        """TC-46: BotRecoveryManager restores session and portfolio cleanly."""
        self.orchestrator.start()
        self.orchestrator.save_checkpoint()

        rec_mgr = BotRecoveryManager(
            session_store=self.session_store,
            checkpoint_manager=self.checkpoint_manager,
        )
        ok, err, comps = rec_mgr.recover_session(
            session_id=self.session_id,
            expected_config_hash=self.orchestrator.session.risk_config_hash,
        )
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIn("session", comps)
        self.assertIn("checkpoint", comps)
        self.assertIn("portfolio", comps)

    def test_47_recovery_fails_on_config_drift(self):
        """TC-47: Recovery fails when risk config hash differs from checkpoint."""
        self.orchestrator.start()
        self.orchestrator.save_checkpoint()

        rec_mgr = BotRecoveryManager(
            session_store=self.session_store,
            checkpoint_manager=self.checkpoint_manager,
        )
        ok, err, _ = rec_mgr.recover_session(
            session_id=self.session_id,
            expected_config_hash="DIFFERENT_HASH_123456",
        )
        self.assertFalse(ok)
        self.assertIn("Configuration hash mismatch", err)

    def test_48_recovery_reconciliation_check(self):
        """TC-48: Recovery produces clean reconciliation report."""
        self.orchestrator.start()
        self.orchestrator.save_checkpoint()

        rec_mgr = BotRecoveryManager(
            session_store=self.session_store,
            checkpoint_manager=self.checkpoint_manager,
        )
        ok, _, comps = rec_mgr.recover_session(session_id=self.session_id)
        self.assertTrue(ok)
        report = comps["reconciliation_report"]
        self.assertEqual(report.status, "BALANCED")
        self.assertEqual(len(report.discrepancies), 0)

    def test_49_journal_deduplication_persists(self):
        """TC-49: BotEventJournal persists processed bar keys and prevents re-execution."""
        journal1 = BotEventJournal(session_id=self.session_id)
        journal1.record_processed_event(bar_key="NVDA:1m:2026-11-23T10:00:00Z", event_id="evt_01")

        # New instance for same session
        journal2 = BotEventJournal(session_id=self.session_id)
        self.assertTrue(journal2.is_processed("NVDA:1m:2026-11-23T10:00:00Z", "evt_01"))

    # =========================================================================
    # Group G: Performance & Health Monitoring (TC 50 - 56)
    # =========================================================================

    def test_50_health_monitor_heartbeat_and_latency(self):
        """TC-50: Health monitor updates latency and event counts upon processing."""
        health = self.orchestrator.health_monitor
        self.assertEqual(health.events_processed_count, 0)

        health.record_event_processed(latency_ms=12.5)
        self.assertEqual(health.events_processed_count, 1)
        self.assertEqual(health.event_processing_latency_ms, 12.5)

    def test_51_health_monitor_queue_depth(self):
        """TC-51: Health monitor snapshot accurately reports current queue depth."""
        self.orchestrator.event_loop.enqueue_event(self._create_bar(minute_offset=1))
        self.orchestrator.event_loop.enqueue_event(self._create_bar(minute_offset=2))

        status = self.orchestrator.get_health()
        self.assertEqual(status["queue_depth"], 2)

    def test_52_health_monitor_feed_staleness(self):
        """TC-52: Health monitor trips STALE_FEED warning when last processed bar is too old."""
        health = self.orchestrator.health_monitor
        health.record_event_processed(latency_ms=5.0)

        # Artificially age last_event_processed_at by 400 seconds
        health.last_event_processed_at = datetime.now(timezone.utc) - timedelta(seconds=400)
        is_stale = health.check_feed_staleness(max_age_seconds=300)
        self.assertTrue(is_stale)
        self.assertEqual(health.consumer_health, "STALE_FEED")

    def test_53_performance_reporter_metrics(self):
        """TC-53: Performance reporter aggregates financial and trade statistics."""
        self.orchestrator.start()
        report = self.orchestrator.get_performance_report()

        self.assertIn("financial", report)
        self.assertEqual(report["financial"]["initial_equity"], 100000.0)
        self.assertEqual(report["financial"]["current_equity"], 100000.0)
        self.assertEqual(report["financial"]["total_return_pct"], 0.0)
        self.assertEqual(report["financial"]["realized_pnl"], 0.0)

    def test_54_performance_reporter_signal_funnel(self):
        """TC-54: Performance reporter accurately tracks signal conversion funnel."""
        reporter = BotPerformanceReporter(self.session_id)
        rep = reporter.generate_report(
            session=self.session,
            portfolio=self.portfolio,
            orders=[],
            fills=[],
            signals_received=15,
            signals_accepted=10,
            signals_rejected=5,
        )
        self.assertEqual(rep["signals"]["signals_received"], 15)
        self.assertEqual(rep["signals"]["signals_accepted"], 10)
        self.assertEqual(rep["signals"]["signals_rejected"], 5)
        self.assertAlmostEqual(rep["signals"]["acceptance_rate_pct"], 66.67, places=2)

    def test_55_performance_reporter_persistence(self):
        """TC-55: Generated performance report is stored on disk."""
        self.orchestrator.start()
        self.orchestrator.get_performance_report()
        expected_path = os.path.join(
            self.orchestrator.performance_reporter.storage_dir,
            f"perf_{self.session_id}.json",
        )
        self.assertTrue(os.path.exists(expected_path))

    def test_56_command_service_get_bot_status(self):
        """TC-56: CommandService get_bot_status returns full status dictionary."""
        cmd_svc = BotCommandService(session_store=self.session_store)
        orch = cmd_svc.create_bot(bot_id="b_stat_test", initial_cash=75000.0)
        s_id = orch.session.bot_session_id

        status = cmd_svc.get_bot_status(s_id)
        self.assertEqual(status["session_id"], s_id)
        self.assertEqual(status["lifecycle_state"], BotLifecycleState.STOPPED)
        self.assertEqual(status["portfolio_equity"], 75000.0)
        self.assertEqual(status["open_positions"], 0)

    # =========================================================================
    # Group H: Safety Invariants & Sandbox Isolation (TC 57 - 65)
    # =========================================================================

    def test_57_invariant_trading_mode_dry_run(self):
        """TC-57: Safety Invariant — trading_mode is strictly DRY_RUN."""
        self.assertEqual(self.orchestrator.session.trading_mode, "DRY_RUN")

    def test_58_invariant_paper_gate_closed(self):
        """TC-58: Safety Invariant — AlpacaPaperGate.is_gate_open remains False."""
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)

    def test_59_invariant_no_alpaca_broker_calls(self):
        """TC-59: Safety Invariant — simulation broker does not instantiate Alpaca trading client."""
        # Broker has no alpaca attribute
        self.assertFalse(hasattr(self.simulation_broker, "alpaca_client"))
        self.assertFalse(hasattr(self.simulation_broker, "trading_client"))

    def test_60_invariant_all_entities_simulation(self):
        """TC-60: Safety Invariant — all session, order, fill, and checkpoint entities bear environment=SIMULATION."""
        self.assertEqual(self.session.environment, "SIMULATION")
        self.assertEqual(self.portfolio.get_portfolio_snapshot().environment, "SIMULATION")
        self.assertEqual(SimulatedOrder().environment, "SIMULATION")
        self.assertEqual(SimulatedFill().environment, "SIMULATION")

        cp = self.orchestrator.save_checkpoint()
        self.assertEqual(cp.environment, "SIMULATION")

    def test_61_invariant_isolated_test_storage(self):
        """TC-61: Safety Invariant — storage operates strictly in isolated test directories."""
        self.assertTrue(self.session_store.storage_dir.startswith(self.test_dir))
        self.assertTrue(self.checkpoint_manager.storage_dir.startswith(self.test_dir))

    def test_62_invariant_dedicated_consumer_group(self):
        """TC-62: Safety Invariant — consumer group is dedicated paper-bot-v2-group."""
        self.assertEqual(self.session.data_consumer_group, "paper-bot-v2-group")

    def test_63_invariant_event_loop_blocks_live_data(self):
        """TC-63: Safety Invariant — event loop violently rejects live data injection."""
        live_bar = self._create_bar(minute_offset=1, environment="PRODUCTION_LIVE")
        with self.assertRaises(ValueError) as ctx:
            self.orchestrator.event_loop.enqueue_event(live_bar)
        self.assertIn("Security error", str(ctx.exception))

    def test_64_invariant_reconciliation_clean(self):
        """TC-64: Safety Invariant — broker reconciliation passes with zero discrepancy."""
        rec = self.simulation_broker.reconcile()
        self.assertEqual(rec.status, "BALANCED")
        self.assertEqual(len(rec.discrepancies), 0)

    def test_65_full_e2e_multi_bar_orchestration_cycle(self):
        """
        TC-65: Full multi-bar lifecycle integration test:
        1. Start bot (RUNNING).
        2. Feed Bar 1 -> HOLD.
        3. Feed Bar 2 -> BUY signal -> Intent -> WORKING order.
        4. Feed Bar 3 -> Broker matches order -> FILLED -> Position created.
        5. Pause bot -> Checkpoint saved.
        6. Resume bot.
        7. Stop bot -> CANCEL_REMAINDER applied -> Final checkpoint & perf report verified.
        """
        # 1. Start
        self.orchestrator.start()
        self.assertEqual(self.orchestrator.state, BotLifecycleState.RUNNING)

        # 2. Bar 1 (Hold)
        b1 = self._create_bar(minute_offset=1, price=140.0)
        res1 = self.orchestrator.submit_bar(b1, auto_process=True)
        self.assertEqual(res1["status"], "PROCESSED")
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 0)

        # 3. Bar 2 (Triggers BUY signal)
        b2 = self._create_bar(minute_offset=2, price=141.0)
        res2 = self.orchestrator.submit_bar(b2, auto_process=True)
        self.assertEqual(res2["status"], "PROCESSED")
        self.assertIsNotNone(res2["signal"])
        self.assertEqual(res2["signal"].signal_type, "BUY")
        open_orders = self.simulation_broker.order_manager.get_open_orders()
        self.assertEqual(len(open_orders), 1)
        self.assertEqual(open_orders[0].status, OrderState.WORKING)

        # 4. Bar 3 (Fills the pending order)
        b3 = self._create_bar(minute_offset=3, price=142.0)
        res3 = self.orchestrator.submit_bar(b3, auto_process=True)
        self.assertEqual(res3["fills_generated"], 1)
        self.assertEqual(len(self.simulation_broker.order_manager.get_open_orders()), 0)

        # Verify position created
        pos = self.portfolio.positions.get_position("NVDA")
        self.assertIsNotNone(pos)
        self.assertTrue(pos.qty > 0)

        # 5. Pause
        self.orchestrator.pause()
        self.assertEqual(self.orchestrator.state, BotLifecycleState.PAUSED)
        cp_pause = self.checkpoint_manager.load_checkpoint(self.session_id)
        self.assertIsNotNone(cp_pause)

        # 6. Resume
        self.orchestrator.resume()
        self.assertEqual(self.orchestrator.state, BotLifecycleState.RUNNING)

        # 7. Stop
        self.orchestrator.stop(policy=StopPolicy.CANCEL_REMAINDER)
        self.assertEqual(self.orchestrator.state, BotLifecycleState.STOPPED)

        # Check final checkpoint & report
        cp_final = self.checkpoint_manager.load_checkpoint(self.session_id)
        self.assertIsNotNone(cp_final)
        self.assertEqual(cp_final.reconciliation_status, "BALANCED")

        perf = self.orchestrator.get_performance_report()
        self.assertEqual(perf["trades"]["total_trades"], 1)
        self.assertTrue(perf["signals"]["signals_accepted"] >= 1)


if __name__ == "__main__":
    unittest.main()
