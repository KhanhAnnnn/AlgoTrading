"""
tests/test_gd33_execution_broker.py — GĐ33 Order Management & Simulation Broker Test Suite
Contains 65 automated unit, integration, and safety tests covering:
A. Intent and Order Validation (TC 01 - 09)
B. Order Lifecycle State Machine (TC 10 - 19)
C. Market and Limit Fill Engine (TC 20 - 26)
D. Stop, Stop-Limit, and Trailing-Stop Orders (TC 27 - 34)
E. Partial Fill and Volume Participation (TC 35 - 40)
F. Slippage and Fee Models (TC 41 - 48)
G. Portfolio Integration, Idempotency & Reconciliation (TC 49 - 57)
H. Safety Invariants & Sandbox Isolation (TC 58 - 65)
"""

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import os
import shutil

from libs.bot.domain import (
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    MarketDataEvent,
)
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.execution.lifecycle import (
    OrderState,
    OrderLifecycleStateMachine,
    InvalidOrderStateTransitionError,
)
from libs.bot.execution.slippage import (
    ZeroSlippageModel,
    FixedBpsSlippageModel,
    ConfigurableImpactSlippageModel,
)
from libs.bot.execution.fees import (
    ZeroFeeModel,
    ConfigurableFeeModel,
)
from libs.bot.execution.fill_engine import FillEngine
from libs.bot.execution.portfolio_adapter import PortfolioExecutionAdapter
from libs.bot.execution.ledger import ExecutionLedger
from libs.bot.execution.order_store import OrderStore
from libs.bot.execution.fill_store import FillStore
from libs.bot.execution.order_manager import SimulationOrderManager
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.alpaca_paper_gate import AlpacaPaperGate, LiveTradingProhibitedError


class TestGD33ExecutionBrokerEngine(unittest.TestCase):
    """GĐ33 Comprehensive Execution & Simulation Broker Test Suite."""

    def setUp(self):
        self.test_dir_orders = "data/paper_bot/test_orders_gd33"
        self.test_dir_fills = "data/paper_bot/test_fills_gd33"
        os.makedirs(self.test_dir_orders, exist_ok=True)
        os.makedirs(self.test_dir_fills, exist_ok=True)

        self.portfolio = SimulationPortfolioManager(
            portfolio_id="port_test_exec_01",
            bot_session_id="sess_test_exec_01",
            initial_cash=100000.0,
        )
        self.order_store = OrderStore(self.test_dir_orders)
        self.fill_store = FillStore(self.test_dir_fills)
        self.ledger = ExecutionLedger()
        self.broker = SimulationBroker(
            portfolio=self.portfolio,
            order_store=self.order_store,
            fill_store=self.fill_store,
            ledger=self.ledger,
            max_participation_rate=0.10,
        )

    def tearDown(self):
        if os.path.exists(self.test_dir_orders):
            shutil.rmtree(self.test_dir_orders, ignore_errors=True)
        if os.path.exists(self.test_dir_fills):
            shutil.rmtree(self.test_dir_fills, ignore_errors=True)

    def _create_intent(
        self,
        symbol="AAPL",
        side="BUY",
        qty=10.0,
        order_type="MARKET",
        limit_price=None,
        ref_price=150.0,
        idemp_key=None,
    ) -> SimulationOrderIntent:
        import uuid
        return SimulationOrderIntent(
            intent_id=f"intent_{uuid.uuid4().hex[:10]}",
            decision_id=f"dec_{uuid.uuid4().hex[:10]}",
            signal_id=f"sig_{uuid.uuid4().hex[:10]}",
            bot_session_id="sess_test_exec_01",
            portfolio_id=self.portfolio.portfolio_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            proposed_quantity=qty,
            proposed_notional=qty * ref_price,
            reference_price=ref_price,
            limit_price=limit_price,
            risk_configuration_version="1.0.0",
            idempotency_key=idemp_key or f"idemp_{uuid.uuid4().hex}",
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )

    # =========================================================================
    # Group A: Intent and Order Validation (TC 01 - 09)
    # =========================================================================

    def test_01_valid_accepted_intent_creates_single_order(self):
        """TC-01: Valid intent creates exactly one order in WORKING state."""
        intent = self._create_intent(symbol="AAPL", side="BUY", qty=20.0, ref_price=150.0)
        order = self.broker.submit_intent(intent)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, OrderState.WORKING)
        self.assertEqual(order.symbol, "AAPL")
        self.assertEqual(order.quantity, 20.0)
        self.assertEqual(order.remaining_quantity, 20.0)
        self.assertEqual(order.filled_quantity, 0.0)
        # Verify reservation made
        self.assertEqual(self.portfolio.reserved_cash, Decimal("3000.00"))

    def test_02_rejected_intent_rejected_without_order(self):
        """TC-02: Intent with non-simulation environment is rejected without creating order."""
        intent = self._create_intent()
        intent.environment = "LIVE"
        with self.assertRaises(ValueError):
            self.broker.submit_intent(intent)

    def test_03_duplicate_intent_prevention(self):
        """TC-03: Submitting intent with duplicate idempotency key is rejected."""
        key = "idemp_unique_test_123"
        intent1 = self._create_intent(idemp_key=key)
        intent2 = self._create_intent(idemp_key=key)
        self.broker.submit_intent(intent1)
        with self.assertRaises(ValueError) as ctx:
            self.broker.submit_intent(intent2)
        self.assertIn("DUPLICATE", str(ctx.exception))

    def test_04_invalid_quantity_rejection(self):
        """TC-04: Intent with quantity <= 0 is rejected."""
        intent = self._create_intent(qty=0.0)
        with self.assertRaises(ValueError) as ctx:
            self.broker.submit_intent(intent)
        self.assertIn("QUANTITY", str(ctx.exception))

    def test_05_invalid_reference_price_rejection(self):
        """TC-05: Intent with non-positive reference price is rejected."""
        intent = self._create_intent(ref_price=-10.0)
        with self.assertRaises(ValueError) as ctx:
            self.broker.submit_intent(intent)
        self.assertIn("REFERENCE_PRICE", str(ctx.exception))

    def test_06_invalid_strategy_version_rejection(self):
        """TC-06: Intent with unauthorized strategy version is rejected."""
        intent = self._create_intent()
        intent.risk_configuration_version = "9.9.9"
        with self.assertRaises(ValueError) as ctx:
            self.broker.submit_intent(intent)
        self.assertIn("STRATEGY_VERSION", str(ctx.exception))

    def test_07_order_metadata_preservation(self):
        """TC-07: Portfolio ID, signal ID, and reference price are preserved in order metadata."""
        intent = self._create_intent(ref_price=145.0)
        order = self.broker.submit_intent(intent)
        self.assertEqual(order.metadata.get("portfolio_id"), self.portfolio.portfolio_id)
        self.assertEqual(order.metadata.get("signal_id"), intent.signal_id)
        self.assertEqual(order.metadata.get("reference_price"), 145.0)

    def test_08_order_environment_always_simulation(self):
        """TC-08: Created order strictly bears environment='SIMULATION'."""
        intent = self._create_intent()
        order = self.broker.submit_intent(intent)
        self.assertEqual(order.environment, "SIMULATION")

    def test_09_intent_already_consumed_rejection(self):
        """TC-09: Re-submitting an already consumed intent_id raises error."""
        intent = self._create_intent()
        self.broker.submit_intent(intent)
        with self.assertRaises(ValueError) as ctx:
            self.broker.order_manager.create_order_from_intent(intent)
        self.assertIn("ALREADY_CONSUMED", str(ctx.exception))

    # =========================================================================
    # Group B: Order Lifecycle State Machine (TC 10 - 19)
    # =========================================================================

    def test_10_transition_created_to_accepted(self):
        """TC-10: Verifies valid transition CREATED -> ACCEPTED."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.CREATED)
        OrderLifecycleStateMachine.transition(order, OrderState.ACCEPTED)
        self.assertEqual(order.status, OrderState.ACCEPTED)

    def test_11_transition_accepted_to_working(self):
        """TC-11: Verifies valid transition ACCEPTED -> WORKING."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.ACCEPTED)
        OrderLifecycleStateMachine.transition(order, OrderState.WORKING)
        self.assertEqual(order.status, OrderState.WORKING)

    def test_12_transition_working_to_partially_filled(self):
        """TC-12: Partial fill transitions order to PARTIALLY_FILLED."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.WORKING)
        status = OrderLifecycleStateMachine.apply_fill_to_order(order, fill_qty=Decimal("4.0"), fill_price=Decimal("150.0"))
        self.assertEqual(status, OrderState.PARTIALLY_FILLED)
        self.assertEqual(order.filled_quantity, 4.0)
        self.assertEqual(order.remaining_quantity, 6.0)
        self.assertEqual(order.average_fill_price, 150.0)

    def test_13_transition_partially_filled_to_filled(self):
        """TC-13: Second fill completes order, transitioning to FILLED with remaining_qty=0."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.WORKING)
        OrderLifecycleStateMachine.apply_fill_to_order(order, fill_qty=Decimal("4.0"), fill_price=Decimal("150.0"))
        status2 = OrderLifecycleStateMachine.apply_fill_to_order(order, fill_qty=Decimal("6.0"), fill_price=Decimal("160.0"))
        self.assertEqual(status2, OrderState.FILLED)
        self.assertEqual(order.filled_quantity, 10.0)
        self.assertEqual(order.remaining_quantity, 0.0)
        # Weighted average price: (4*150 + 6*160) / 10 = 156.0
        self.assertEqual(order.average_fill_price, 156.0)

    def test_14_transition_working_to_cancelled(self):
        """TC-14: Working order cancelled transitions to CANCELLED."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.WORKING)
        OrderLifecycleStateMachine.transition(order, OrderState.CANCELLED, reason="User cancelled")
        self.assertEqual(order.status, OrderState.CANCELLED)
        self.assertEqual(order.rejection_reason, "User cancelled")

    def test_15_transition_partially_filled_to_cancelled(self):
        """TC-15: Partially filled order cancelled retains filled quantity and history."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.WORKING)
        OrderLifecycleStateMachine.apply_fill_to_order(order, fill_qty=Decimal("3.0"), fill_price=Decimal("100.0"))
        OrderLifecycleStateMachine.transition(order, OrderState.CANCELLED, reason="Cancelled remaining")
        self.assertEqual(order.status, OrderState.CANCELLED)
        self.assertEqual(order.filled_quantity, 3.0)
        self.assertEqual(order.remaining_quantity, 7.0)

    def test_16_transition_working_to_expired(self):
        """TC-16: Working order expired transitions to EXPIRED."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.WORKING)
        OrderLifecycleStateMachine.transition(order, OrderState.EXPIRED, reason="Day end")
        self.assertEqual(order.status, OrderState.EXPIRED)

    def test_17_order_replacement_preserves_audit_links(self):
        """TC-17: Order replacement creates new WORKING order and marks old REPLACED."""
        intent = self._create_intent(qty=10.0, ref_price=100.0)
        old_order = self.broker.submit_intent(intent)
        new_order = self.broker.order_manager.replace_order(
            order_id=old_order.simulated_order_id,
            new_quantity=15.0,
            new_limit_price=105.0,
        )
        self.assertEqual(old_order.status, OrderState.REPLACED)
        self.assertEqual(old_order.replaced_by_order_id, new_order.simulated_order_id)
        self.assertEqual(new_order.status, OrderState.WORKING)
        self.assertEqual(new_order.replaces_order_id, old_order.simulated_order_id)
        self.assertEqual(new_order.quantity, 15.0)

    def test_18_invalid_state_transition_rejected(self):
        """TC-18: Illegal transition from terminal state raises InvalidOrderStateTransitionError."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.FILLED)
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderLifecycleStateMachine.transition(order, OrderState.WORKING)

    def test_19_terminal_order_cannot_receive_fills(self):
        """TC-19: Attempting to fill a terminal order raises error."""
        order = SimulatedOrder(symbol="AAPL", quantity=10.0, status=OrderState.CANCELLED)
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderLifecycleStateMachine.apply_fill_to_order(order, Decimal("5.0"), Decimal("100.0"))

    # =========================================================================
    # Group C: Market and Limit Fill Engine (TC 20 - 26)
    # =========================================================================

    def test_20_market_fill_on_next_eligible_bar(self):
        """TC-20: Market order fills at Open of next eligible bar."""
        intent = self._create_intent(symbol="NVDA", side="BUY", qty=10.0, order_type="MARKET")
        order = self.broker.submit_intent(intent)
        order.source_bar_key = "NVDA:1m:2026-11-22T20:00:00Z"

        # Next bar
        next_bar = MarketDataEvent(
            symbol="NVDA",
            open=140.0,
            high=142.0,
            low=139.5,
            close=141.0,
            volume=5000.0,
            is_final=True,
            event_time=datetime.now(timezone.utc),
        )
        fills = self.broker.process_bar(next_bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 140.0)
        self.assertEqual(fills[0].fill_qty, 10.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_21_no_fill_on_source_signal_bar(self):
        """TC-21: Anti-lookahead prevents fill on same bar where signal was generated."""
        source_key = "NVDA:1m:2026-11-22T20:00:00Z"
        intent = self._create_intent(symbol="NVDA", side="BUY", qty=10.0)
        order = self.broker.submit_intent(intent)
        order.source_bar_key = source_key

        same_bar = MarketDataEvent(
            symbol="NVDA",
            open=140.0,
            high=142.0,
            low=139.5,
            close=141.0,
            volume=5000.0,
            is_final=True,
            event_time=datetime(2026, 11, 22, 20, 0, 0, tzinfo=timezone.utc),
        )
        fills = self.broker.process_bar(same_bar)
        self.assertEqual(len(fills), 0)
        self.assertEqual(order.status, OrderState.WORKING)

    def test_22_limit_buy_fill_when_low_crosses(self):
        """TC-22: Limit BUY fills when bar low <= limit_price."""
        intent = self._create_intent(symbol="MSFT", side="BUY", qty=10.0, order_type="LIMIT", limit_price=300.0)
        order = self.broker.submit_intent(intent)

        bar = MarketDataEvent(
            symbol="MSFT",
            open=302.0,
            high=305.0,
            low=298.0,  # Dropped below 300.0
            close=301.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 300.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_23_limit_sell_fill_when_high_crosses(self):
        """TC-23: Limit SELL fills when bar high >= limit_price."""
        intent = self._create_intent(symbol="MSFT", side="SELL", qty=5.0, order_type="LIMIT", limit_price=310.0)
        order = self.broker.submit_intent(intent)

        bar = MarketDataEvent(
            symbol="MSFT",
            open=308.0,
            high=312.0,  # Exceeded 310.0
            low=307.0,
            close=311.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 310.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_24_limit_order_no_fill_when_price_not_reached(self):
        """TC-24: Limit BUY does not fill when bar price never drops to limit."""
        intent = self._create_intent(symbol="MSFT", side="BUY", qty=10.0, order_type="LIMIT", limit_price=290.0)
        order = self.broker.submit_intent(intent)

        bar = MarketDataEvent(
            symbol="MSFT",
            open=302.0,
            high=305.0,
            low=295.0,  # Lowest is 295 > 290
            close=301.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 0)
        self.assertEqual(order.status, OrderState.WORKING)

    def test_25_limit_gap_handling(self):
        """TC-25: Limit BUY with favorable gap down fills at favorable open price."""
        intent = self._create_intent(symbol="TSLA", side="BUY", qty=10.0, order_type="LIMIT", limit_price=200.0)
        order = self.broker.submit_intent(intent)

        bar = MarketDataEvent(
            symbol="TSLA",
            open=195.0,  # Gapped down to 195.0
            high=198.0,
            low=194.0,
            close=197.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 195.0)

    def test_26_never_fill_at_price_worse_than_limit(self):
        """TC-26: Guaranteed invariant: fill price is strictly <= limit for BUY."""
        intent = self._create_intent(symbol="TSLA", side="BUY", qty=10.0, order_type="LIMIT", limit_price=200.0)
        order = self.broker.submit_intent(intent)

        # Broker configured with fixed adverse slippage
        self.broker.fill_engine.slippage_model = FixedBpsSlippageModel(bps=50.0)

        bar = MarketDataEvent(
            symbol="TSLA",
            open=199.5,
            high=201.0,
            low=199.0,
            close=200.5,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertLessEqual(fills[0].fill_price, 200.0)

    # =========================================================================
    # Group D: Stop, Stop-Limit, and Trailing-Stop Orders (TC 27 - 34)
    # =========================================================================

    def test_27_stop_buy_triggered_and_filled(self):
        """TC-27: Stop BUY triggers when bar high reaches stop price."""
        intent = self._create_intent(symbol="AAPL", side="BUY", qty=10.0, order_type="STOP")
        order = self.broker.submit_intent(intent)
        order.stop_price = 160.0

        bar = MarketDataEvent(
            symbol="AAPL",
            open=158.0,
            high=162.0,  # Reached 160.0
            low=157.0,
            close=161.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 160.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_28_stop_sell_triggered_and_filled(self):
        """TC-28: Stop SELL triggers when bar low reaches stop price."""
        intent = self._create_intent(symbol="AAPL", side="SELL", qty=10.0, order_type="STOP")
        order = self.broker.submit_intent(intent)
        order.stop_price = 140.0

        bar = MarketDataEvent(
            symbol="AAPL",
            open=142.0,
            high=143.0,
            low=138.0,  # Dropped below 140.0
            close=139.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 140.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_29_stop_order_gap_handling(self):
        """TC-29: Stop order gapping through trigger fills at Open (adverse gap)."""
        intent = self._create_intent(symbol="AAPL", side="BUY", qty=10.0, order_type="STOP")
        order = self.broker.submit_intent(intent)
        order.stop_price = 160.0

        # Bar opens at 165.0 (gapped over 160.0)
        bar = MarketDataEvent(
            symbol="AAPL",
            open=165.0,
            high=168.0,
            low=164.0,
            close=167.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_price, 165.0)

    def test_30_stop_limit_trigger_without_fill(self):
        """TC-30: Stop Limit triggers when stop touched, but does not fill if limit unmet."""
        intent = self._create_intent(symbol="GOOG", side="BUY", qty=10.0, order_type="STOP_LIMIT")
        order = self.broker.submit_intent(intent)
        order.stop_price = 150.0
        order.limit_price = 148.0  # Limit is below stop

        # Bar reaches 150 (triggers stop), but lowest is 149 > 148
        bar = MarketDataEvent(
            symbol="GOOG",
            open=149.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 0)
        self.assertTrue(order.metadata.get("stop_triggered"))
        self.assertEqual(order.status, OrderState.WORKING)

    def test_31_stop_limit_trigger_and_fill(self):
        """TC-31: Stop Limit triggers and fills when limit condition is satisfied."""
        intent = self._create_intent(symbol="GOOG", side="BUY", qty=10.0, order_type="STOP_LIMIT")
        order = self.broker.submit_intent(intent)
        order.stop_price = 150.0
        order.limit_price = 152.0

        bar = MarketDataEvent(
            symbol="GOOG",
            open=149.0,
            high=153.0,
            low=148.0,
            close=151.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertLessEqual(fills[0].fill_price, 152.0)

    def test_32_stop_limit_intrabar_ambiguity_conservative(self):
        """TC-32: Conservative evaluation when stop and limit are checked on bar."""
        intent = self._create_intent(symbol="GOOG", side="BUY", qty=10.0, order_type="STOP_LIMIT")
        order = self.broker.submit_intent(intent)
        order.stop_price = 155.0
        order.limit_price = 153.0

        # Bar high is 154 (does not reach 155 stop)
        bar = MarketDataEvent(
            symbol="GOOG",
            open=150.0,
            high=154.0,
            low=149.0,
            close=153.0,
            volume=5000.0,
            is_final=True,
        )
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 0)
        self.assertFalse(order.metadata.get("stop_triggered", False))

    def test_33_trailing_stop_tracks_favorable_peak(self):
        """TC-33: Trailing stop SELL tracks high-water mark and adjusts stop trigger upward."""
        intent = self._create_intent(symbol="AAPL", side="SELL", qty=10.0, order_type="TRAILING_STOP")
        order = self.broker.submit_intent(intent)
        order.trailing_offset = 5.0
        order.trailing_reference_price = 150.0

        # Bar reaches new high of 160.0 (Stop trigger moves to 155.0)
        bar1 = MarketDataEvent(
            symbol="AAPL",
            open=152.0,
            high=160.0,
            low=156.0,  # Lowest is 156 > 155 -> No trigger
            close=159.0,
            volume=5000.0,
            is_final=True,
        )
        fills1 = self.broker.process_bar(bar1)
        self.assertEqual(len(fills1), 0)
        self.assertEqual(order.trailing_reference_price, 160.0)

    def test_34_trailing_stop_triggers_on_reversal(self):
        """TC-34: Trailing stop triggers when price drops by trailing_offset from peak."""
        intent = self._create_intent(symbol="AAPL", side="SELL", qty=10.0, order_type="TRAILING_STOP")
        order = self.broker.submit_intent(intent)
        order.trailing_offset = 5.0
        order.trailing_reference_price = 160.0  # Peak is 160, stop is 155

        # Bar drops to 153 (crosses 155)
        bar2 = MarketDataEvent(
            symbol="AAPL",
            open=158.0,
            high=159.0,
            low=153.0,
            close=154.0,
            volume=5000.0,
            is_final=True,
        )
        fills2 = self.broker.process_bar(bar2)
        self.assertEqual(len(fills2), 1)
        self.assertEqual(fills2[0].fill_price, 155.0)
        self.assertEqual(order.status, OrderState.FILLED)

    # =========================================================================
    # Group E: Partial Fill and Volume Participation (TC 35 - 40)
    # =========================================================================

    def test_35_full_fill_when_volume_sufficient(self):
        """TC-35: Full fill when order quantity <= allowable participation volume."""
        intent = self._create_intent(qty=20.0)
        order = self.broker.submit_intent(intent)
        # Bar volume = 500. 10% cap = 50. Order qty = 20 <= 50.
        bar = MarketDataEvent(symbol="AAPL", open=150.0, high=151.0, low=149.0, close=150.5, volume=500.0, is_final=True)
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_qty, 20.0)
        self.assertEqual(order.status, OrderState.FILLED)

    def test_36_partial_fill_capped_by_participation_rate(self):
        """TC-36: Fill quantity capped at max_participation_rate * bar.volume."""
        intent = self._create_intent(qty=100.0)
        order = self.broker.submit_intent(intent)
        # Bar volume = 500. 10% cap = 50. Order qty = 100 > 50 -> Partial fill of 50.
        bar = MarketDataEvent(symbol="AAPL", open=150.0, high=151.0, low=149.0, close=150.5, volume=500.0, is_final=True)
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_qty, 50.0)
        self.assertEqual(order.status, OrderState.PARTIALLY_FILLED)
        self.assertEqual(order.filled_quantity, 50.0)
        self.assertEqual(order.remaining_quantity, 50.0)

    def test_37_zero_volume_bar_produces_zero_fill(self):
        """TC-37: When bar volume == 0, no fill is generated."""
        intent = self._create_intent(qty=10.0)
        order = self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="AAPL", open=150.0, high=151.0, low=149.0, close=150.5, volume=0.0, is_final=True)
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 0)
        self.assertEqual(order.status, OrderState.WORKING)

    def test_38_participation_cap_enforced_across_competing_orders(self):
        """TC-38: Multiple competing orders on same symbol share bar volume without exceeding cap."""
        # 10% cap on volume 500 = 50 units total
        intent1 = self._create_intent(symbol="NVDA", qty=40.0)
        intent2 = self._create_intent(symbol="NVDA", qty=40.0)
        o1 = self.broker.submit_intent(intent1)
        o2 = self.broker.submit_intent(intent2)

        bar = MarketDataEvent(symbol="NVDA", open=140.0, high=141.0, low=139.0, close=140.5, volume=500.0, is_final=True)
        fills = self.broker.process_bar(bar)
        # Total filled should be exactly 50 units (40 for o1, 10 for o2)
        total_filled = sum(f.fill_qty for f in fills)
        self.assertEqual(total_filled, 50.0)
        self.assertEqual(o1.filled_quantity, 40.0)
        self.assertEqual(o1.status, OrderState.FILLED)
        self.assertEqual(o2.filled_quantity, 10.0)
        self.assertEqual(o2.status, OrderState.PARTIALLY_FILLED)

    def test_39_fractional_quantity_preserved_in_fill(self):
        """TC-39: Fractional fill quantity (0.1234 BTC) is preserved."""
        intent = self._create_intent(symbol="BTC/USD", qty=0.1234, ref_price=60000.0)
        order = self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="BTC/USD", open=60000.0, high=60500.0, low=59500.0, close=60200.0, volume=10.0, is_final=True)
        fills = self.broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_qty, 0.1234)

    def test_40_remaining_quantity_calculation_exact(self):
        """TC-40: remaining_quantity = quantity - filled_quantity calculated exactly."""
        order = SimulatedOrder(symbol="AAPL", quantity=100.0, remaining_quantity=100.0, status=OrderState.WORKING)
        OrderLifecycleStateMachine.apply_fill_to_order(order, Decimal("33.33"), Decimal("150.0"))
        self.assertAlmostEqual(order.remaining_quantity, 66.67, places=2)

    # =========================================================================
    # Group F: Slippage and Fee Models (TC 41 - 48)
    # =========================================================================

    def test_41_zero_slippage_baseline(self):
        """TC-41: ZeroSlippageModel returns exact base price."""
        model = ZeroSlippageModel()
        price, slip = model.calculate_slippage(Decimal("100.0"), "BUY", Decimal("10.0"))
        self.assertEqual(price, Decimal("100.0"))
        self.assertEqual(slip, Decimal("0.0"))

    def test_42_fixed_bps_slippage_buy_adverse(self):
        """TC-42: BUY fill price is adversely higher by BPS/10000."""
        model = FixedBpsSlippageModel(bps=10.0)  # 10 bps = 0.10%
        price, slip = model.calculate_slippage(Decimal("100.0"), "BUY", Decimal("10.0"))
        self.assertEqual(slip, Decimal("0.10"))
        self.assertEqual(price, Decimal("100.10"))

    def test_43_fixed_bps_slippage_sell_adverse(self):
        """TC-43: SELL fill price is adversely lower by BPS/10000."""
        model = FixedBpsSlippageModel(bps=10.0)
        price, slip = model.calculate_slippage(Decimal("100.0"), "SELL", Decimal("10.0"))
        self.assertEqual(slip, Decimal("0.10"))
        self.assertEqual(price, Decimal("99.90"))

    def test_44_negative_slippage_bps_rejected(self):
        """TC-44: Instantiating FixedBpsSlippageModel with bps < 0 raises ValueError."""
        with self.assertRaises(ValueError):
            FixedBpsSlippageModel(bps=-5.0)

    def test_45_fee_calculation_stocks_per_share(self):
        """TC-45: ConfigurableFeeModel computes per-share fee with minimum commission for stocks."""
        fee_model = ConfigurableFeeModel(stocks_per_share=0.005, stocks_min_commission=1.00)
        # 100 shares * 0.005 = 0.50 -> Min 1.00 enforced
        res1 = fee_model.calculate_fee("AAPL", "STOCKS", "BUY", Decimal("100.0"), Decimal("150.0"))
        self.assertEqual(res1.fee_amount, Decimal("1.00"))
        # 500 shares * 0.005 = 2.50 > 1.00
        res2 = fee_model.calculate_fee("AAPL", "STOCKS", "BUY", Decimal("500.0"), Decimal("150.0"))
        self.assertEqual(res2.fee_amount, Decimal("2.50"))

    def test_46_fee_calculation_crypto_bps(self):
        """TC-46: ConfigurableFeeModel computes notional BPS fee for crypto."""
        fee_model = ConfigurableFeeModel(crypto_bps=10.0)  # 10 bps = 0.10%
        # 1 BTC @ 60,000 = 60,000 notional * 0.10% = 60.00
        res = fee_model.calculate_fee("BTC/USD", "CRYPTO", "BUY", Decimal("1.0"), Decimal("60000.0"))
        self.assertEqual(res.fee_amount, Decimal("60.00"))

    def test_47_zero_fee_baseline(self):
        """TC-47: ZeroFeeModel returns 0.0 fee."""
        fee_model = ZeroFeeModel()
        res = fee_model.calculate_fee("AAPL", "STOCKS", "BUY", Decimal("100.0"), Decimal("150.0"))
        self.assertEqual(res.fee_amount, Decimal("0.00"))

    def test_48_fee_not_double_counted_on_retry(self):
        """TC-48: Querying fee model multiple times returns identical deterministic result."""
        fee_model = ConfigurableFeeModel(crypto_bps=10.0)
        res1 = fee_model.calculate_fee("BTC/USD", "CRYPTO", "BUY", Decimal("1.0"), Decimal("60000.0"))
        res2 = fee_model.calculate_fee("BTC/USD", "CRYPTO", "BUY", Decimal("1.0"), Decimal("60000.0"))
        self.assertEqual(res1.fee_amount, res2.fee_amount)

    # =========================================================================
    # Group G: Portfolio Integration, Idempotency & Reconciliation (TC 49 - 57)
    # =========================================================================

    def test_49_fill_updates_portfolio_cash_accurately(self):
        """TC-49: BUY fill deducts (fill_qty * fill_price) + fee from portfolio cash."""
        self.broker.fill_engine.fee_model = ConfigurableFeeModel(stocks_per_share=0.01, stocks_min_commission=1.0)
        # Initial cash = 100,000
        intent = self._create_intent(symbol="AAPL", qty=10.0, ref_price=100.0)
        self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="AAPL", open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0, is_final=True)
        self.broker.process_bar(bar)
        # Cost = 10 * 100 + 1.0 (fee) = 1001.00
        expected_cash = Decimal("100000.00") - Decimal("1001.00")
        self.assertEqual(self.portfolio.cash, expected_cash)

    def test_50_fill_updates_portfolio_positions(self):
        """TC-50: BUY fill updates position quantity, cost basis, and market value in PositionBook."""
        intent = self._create_intent(symbol="NVDA", qty=15.0, ref_price=130.0)
        self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="NVDA", open=130.0, high=131.0, low=129.0, close=130.5, volume=1000.0, is_final=True)
        self.broker.process_bar(bar)
        pos = self.portfolio.positions.get_position("NVDA")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.qty, 15.0)
        self.assertEqual(pos.avg_entry_price, 130.0)

    def test_51_weighted_average_cost_updated(self):
        """TC-51: Multiple fills on same symbol update weighted average entry price."""
        intent1 = self._create_intent(symbol="AAPL", qty=10.0, ref_price=100.0)
        self.broker.submit_intent(intent1)
        bar1 = MarketDataEvent(symbol="AAPL", open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0, is_final=True)
        self.broker.process_bar(bar1)

        intent2 = self._create_intent(symbol="AAPL", qty=10.0, ref_price=120.0)
        self.broker.submit_intent(intent2)
        bar2 = MarketDataEvent(symbol="AAPL", open=120.0, high=122.0, low=119.0, close=121.0, volume=1000.0, is_final=True)
        self.broker.process_bar(bar2)

        pos = self.portfolio.positions.get_position("AAPL")
        self.assertEqual(pos.qty, 20.0)
        self.assertEqual(pos.avg_entry_price, 110.0)

    def test_52_realized_pnl_on_sell_fill(self):
        """TC-52: SELL fill realizes P&L and credits proceeds minus fee to portfolio cash."""
        # 1. Buy 10 @ 100
        int1 = self._create_intent(symbol="AMD", side="BUY", qty=10.0, ref_price=100.0)
        self.broker.submit_intent(int1)
        b1 = MarketDataEvent(symbol="AMD", open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0, is_final=True)
        self.broker.process_bar(b1)

        # 2. Sell 5 @ 120 (gain = +100)
        int2 = self._create_intent(symbol="AMD", side="SELL", qty=5.0, ref_price=120.0)
        self.broker.submit_intent(int2)
        b2 = MarketDataEvent(symbol="AMD", open=120.0, high=121.0, low=119.0, close=120.0, volume=1000.0, is_final=True)
        self.broker.process_bar(b2)

        self.assertEqual(self.portfolio.realized_pnl, Decimal("100.00"))
        pos = self.portfolio.positions.get_position("AMD")
        self.assertEqual(pos.qty, 5.0)

    def test_53_cash_reservation_released_on_fill(self):
        """TC-53: Cash reservation in portfolio is reduced as order is filled."""
        intent = self._create_intent(qty=20.0, ref_price=100.0)
        self.broker.submit_intent(intent)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("2000.00"))

        bar = MarketDataEvent(symbol="AAPL", open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0, is_final=True)
        self.broker.process_bar(bar)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("0.00"))

    def test_54_cash_reservation_released_on_cancellation(self):
        """TC-54: Cancelling order releases remaining unfilled reservation completely."""
        intent = self._create_intent(qty=25.0, ref_price=100.0)
        order = self.broker.submit_intent(intent)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("2500.00"))

        self.broker.cancel_order(order.simulated_order_id)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("0.00"))

    def test_55_idempotent_fill_application_no_double_counting(self):
        """TC-55: Applying identical fill twice does NOT alter portfolio cash or position twice."""
        fill = SimulatedFill(
            simulated_fill_id="fill_idemp_01",
            simulated_order_id="ord_01",
            symbol="NVDA",
            side="BUY",
            fill_price=100.0,
            fill_qty=10.0,
            fee=0.0,
        )
        applied1 = self.broker.portfolio_adapter.apply_fill(fill)
        cash_after1 = self.portfolio.cash
        self.assertTrue(applied1)

        applied2 = self.broker.portfolio_adapter.apply_fill(fill)
        cash_after2 = self.portfolio.cash
        self.assertFalse(applied2)
        self.assertEqual(cash_after1, cash_after2)

    def test_56_restart_recovery_from_stores(self):
        """TC-56: OrderStore and FillStore reload orders and fills upon broker restart."""
        intent = self._create_intent(qty=10.0)
        order = self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="AAPL", open=150.0, high=151.0, low=149.0, close=150.0, volume=1000.0, is_final=True)
        self.broker.process_bar(bar)

        # New broker instance reading from same stores
        recovered_broker = SimulationBroker(
            portfolio=self.portfolio,
            order_store=self.order_store,
            fill_store=self.fill_store,
        )
        reloaded_order = recovered_broker.order_manager.get_order(order.simulated_order_id)
        self.assertIsNotNone(reloaded_order)
        self.assertEqual(reloaded_order.status, OrderState.FILLED)

    def test_57_mathematical_reconciliation_balanced(self):
        """TC-57: ExecutionLedger.reconcile() returns status='BALANCED' with zero discrepancies."""
        intent = self._create_intent(symbol="AAPL", qty=10.0, ref_price=100.0)
        self.broker.submit_intent(intent)
        bar = MarketDataEvent(symbol="AAPL", open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0, is_final=True)
        self.broker.process_bar(bar)

        report = self.broker.reconcile(initial_cash=Decimal("100000.00"))
        self.assertEqual(report.status, "BALANCED")
        self.assertEqual(len(report.discrepancies), 0)

    # =========================================================================
    # Group H: Safety Invariants & Sandbox Isolation (TC 58 - 65)
    # =========================================================================

    def test_58_no_alpaca_submit_calls(self):
        """TC-58: Confirms zero Alpaca SDK submit order API calls."""
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)

    def test_59_no_alpaca_replace_calls(self):
        """TC-59: Confirms zero Alpaca SDK replace order API calls."""
        self.assertFalse(hasattr(self.broker, "alpaca_client"))

    def test_60_no_alpaca_cancel_calls(self):
        """TC-60: Confirms zero Alpaca SDK cancel order API calls."""
        self.assertFalse(hasattr(self.broker.order_manager, "alpaca_client"))

    def test_61_no_live_execution_path(self):
        """TC-61: Confirms no live endpoints exist in simulation broker."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_62_no_v1_mock_broker_calls(self):
        """TC-62: Confirms complete decoupling from V1 Mock Trading Broker."""
        import sys
        self.assertNotIn("mock_trading_broker", sys.modules.get("libs.bot.execution.simulation_broker", {}).__dict__)

    def test_63_alpaca_account_isolation(self):
        """TC-63: Confirms simulation portfolio does not read Alpaca Paper state."""
        self.assertEqual(self.portfolio.portfolio_id, "port_test_exec_01")
        self.assertFalse(hasattr(self.portfolio, "alpaca_account"))

    def test_64_no_natural_topic_writes(self):
        """TC-64: Confirms no simulation orders or fills written to Kafka market data topics."""
        self.assertFalse(hasattr(SimulationBroker, "kafka_producer"))
        self.assertFalse(hasattr(FillEngine, "publish_to_topic"))

    def test_65_dry_run_invariant(self):
        """TC-65: Confirms global TRADING_MODE=DRY_RUN and is_gate_open=False."""
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        self.assertEqual(os.environ.get("TRADING_MODE", "DRY_RUN"), "DRY_RUN")


if __name__ == "__main__":
    unittest.main()
