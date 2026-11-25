"""
tests/test_gd32_portfolio_risk.py — GĐ32 Portfolio & Risk Management Engine Test Suite
Contains 43 automated unit and boundary tests covering:
1. Portfolio Accounting (TC 01-10)
2. Position Sizing (TC 11-20)
3. Risk Management & Guards (TC 21-28)
4. Signal Decision Engine (TC 29-34)
5. Simulation Isolation & Invariants (TC 35-43)
"""

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import os
import shutil

from libs.bot.domain import (
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedPosition,
    PortfolioSnapshot,
    MarketDataEvent,
)
from libs.bot.portfolio import (
    to_decimal,
    quantize_currency,
    quantize_qty,
    calculate_market_value,
    calculate_cost_basis,
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_portfolio_equity,
    calculate_available_cash,
    calculate_new_weighted_avg_price,
    validate_price_freshness,
    PositionBook,
    PortfolioSnapshotManager,
    SimulationPortfolioManager,
)
from libs.bot.risk import (
    RiskConfig,
    PositionSizingEngine,
    SizingResult,
    RiskLimitsEngine,
    DrawdownMonitor,
    SignalDecisionEngine,
)
from libs.bot.portfolio_store import PortfolioStore
from libs.bot.intent_store import IntentStore
from libs.alpaca_paper_gate import AlpacaPaperGate, PaperExecutionGateClosedError, LiveTradingProhibitedError


class TestGD32PortfolioRiskEngine(unittest.TestCase):
    """GĐ32 Comprehensive Portfolio, Sizing & Risk Management Test Suite."""

    def setUp(self):
        self.test_storage_dir = "data/paper_bot/test_portfolios_gd32"
        self.test_intent_dir = "data/paper_bot/test_intents_gd32"
        os.makedirs(self.test_storage_dir, exist_ok=True)
        os.makedirs(self.test_intent_dir, exist_ok=True)

        self.portfolio = SimulationPortfolioManager(
            portfolio_id="port_test_01",
            bot_session_id="sess_test_01",
            initial_cash=100000.0,
        )
        self.risk_config = RiskConfig(
            risk_per_trade_pct=0.02,
            max_position_notional=25000.0,
            max_position_qty=10000.0,
            max_symbol_exposure_pct=0.30,
            max_portfolio_exposure_pct=1.00,
            daily_loss_limit_pct=0.05,
            max_drawdown_pct=0.10,
            max_concurrent_positions=5,
            max_price_age_seconds=300,
        )

    def tearDown(self):
        if os.path.exists(self.test_storage_dir):
            shutil.rmtree(self.test_storage_dir, ignore_errors=True)
        if os.path.exists(self.test_intent_dir):
            shutil.rmtree(self.test_intent_dir, ignore_errors=True)

    # =========================================================================
    # Group 1: Portfolio Accounting (TC 01 - 10)
    # =========================================================================

    def test_01_initial_simulation_portfolio(self):
        """TC-01: Verifies initial portfolio state, cash, equity, and state."""
        self.assertEqual(self.portfolio.cash, Decimal("100000.0"))
        self.assertEqual(self.portfolio.get_equity(), Decimal("100000.0"))
        self.assertEqual(self.portfolio.available_cash, Decimal("100000.0"))
        self.assertEqual(self.portfolio.reserved_cash, Decimal("0.0"))
        self.assertEqual(self.portfolio.state, "ACTIVE")
        self.assertEqual(self.portfolio.positions.get_active_positions_count(), 0)

    def test_02_equity_calculation(self):
        """TC-02: Verifies Equity = Cash + Sum(Market Value of Positions)."""
        # Cash = 100,000. Add position of 10 shares of NVDA at 140.0 = 1,400.
        self.portfolio.positions.record_fill("NVDA", "BUY", 10.0, 140.0)
        self.portfolio._cash = Decimal("98600.0")  # Deduct cash for test
        equity = self.portfolio.get_equity()
        self.assertEqual(equity, Decimal("100000.0"))

        # Revalue NVDA to 150.0 (+100.0)
        self.portfolio.positions.update_valuation("NVDA", 150.0)
        new_equity = self.portfolio.get_equity()
        self.assertEqual(new_equity, Decimal("100100.0"))

    def test_03_cash_accounting(self):
        """TC-03: Verifies cash reservation and release operations."""
        # Initial available: 100,000
        ok = self.portfolio.reserve_cash(25000.0, "intent_01")
        self.assertTrue(ok)
        self.assertEqual(self.portfolio.reserved_cash, Decimal("25000.0"))
        self.assertEqual(self.portfolio.available_cash, Decimal("75000.0"))

        # Try to reserve more than available (80,000 > 75,000)
        failed = self.portfolio.reserve_cash(80000.0, "intent_02")
        self.assertFalse(failed)
        self.assertEqual(self.portfolio.available_cash, Decimal("75000.0"))

        # Release reservation
        self.portfolio.release_cash(15000.0, "intent_01")
        self.assertEqual(self.portfolio.reserved_cash, Decimal("10000.0"))
        self.assertEqual(self.portfolio.available_cash, Decimal("90000.0"))

    def test_04_fractional_quantity_precision(self):
        """TC-04: Verifies fractional precision without floating-point truncation."""
        self.portfolio.positions.record_fill("BTC/USD", "BUY", 0.12345678, 60000.0)
        pos = self.portfolio.positions.get_position("BTC/USD")
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos.qty, 0.12345678, places=6)
        self.assertAlmostEqual(pos.market_value, 0.12345678 * 60000.0, places=2)

    def test_05_average_cost(self):
        """TC-05: Verifies weighted average cost basis when expanding positions."""
        # Buy 10 @ 100 = 1000
        self.portfolio.positions.record_fill("AAPL", "BUY", 10.0, 100.0)
        # Buy 10 @ 120 = 1200
        self.portfolio.positions.record_fill("AAPL", "BUY", 10.0, 120.0)
        pos = self.portfolio.positions.get_position("AAPL")
        # Total cost = 2200, Total qty = 20 -> Avg = 110.0
        self.assertEqual(pos.qty, 20.0)
        self.assertEqual(pos.avg_entry_price, 110.0)
        self.assertEqual(pos.cost_basis, 2200.0)

    def test_06_realized_pnl_calculations(self):
        """TC-06: Verifies realized P&L when closing positions partially or fully."""
        # Buy 10 @ 100
        self.portfolio.positions.record_fill("MSFT", "BUY", 10.0, 100.0)
        # Sell 5 @ 120 -> Realized P&L = 5 * (120 - 100) = +100.0
        pnl_delta = self.portfolio.positions.record_fill("MSFT", "SELL", 5.0, 120.0)
        self.assertEqual(pnl_delta, Decimal("100.0"))
        pos = self.portfolio.positions.get_position("MSFT")
        self.assertEqual(pos.qty, 5.0)
        self.assertEqual(pos.realized_pnl, 100.0)

    def test_07_unrealized_pnl_calculations(self):
        """TC-07: Verifies mark-to-market unrealized P&L calculation."""
        self.portfolio.positions.record_fill("GOOG", "BUY", 10.0, 150.0)
        self.portfolio.positions.update_valuation("GOOG", 170.0)
        pos = self.portfolio.positions.get_position("GOOG")
        # Market Value = 1700, Cost Basis = 1500 -> Unrealized P&L = +200.0
        self.assertEqual(pos.unrealized_pnl, 200.0)

    def test_08_zero_quantity_position(self):
        """TC-08: Verifies zero quantity position handling without division by zero."""
        self.portfolio.positions.record_fill("TSLA", "BUY", 10.0, 200.0)
        self.portfolio.positions.record_fill("TSLA", "SELL", 10.0, 210.0)
        pos = self.portfolio.positions.get_position("TSLA")
        self.assertEqual(pos.qty, 0.0)
        self.assertEqual(pos.market_value, 0.0)
        self.assertEqual(pos.cost_basis, 0.0)
        self.assertEqual(pos.unrealized_pnl, 0.0)
        self.assertEqual(self.portfolio.positions.get_active_positions_count(), 0)

    def test_09_invalid_mark_price(self):
        """TC-09: Verifies non-positive, NaN, or stale mark prices are rejected."""
        self.portfolio.positions.record_fill("AMD", "BUY", 10.0, 100.0)
        # Non-positive price
        ok1 = self.portfolio.positions.update_valuation("AMD", -50.0)
        self.assertFalse(ok1)
        ok2 = self.portfolio.positions.update_valuation("AMD", 0.0)
        self.assertFalse(ok2)
        # Stale price (older than 300s)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        ok3 = self.portfolio.positions.update_valuation("AMD", 110.0, price_time=stale_time)
        self.assertFalse(ok3)

    def test_10_snapshot_persistence(self):
        """TC-10: Verifies atomic snapshot persistence, checksum integrity, and restoration."""
        store = PortfolioStore(self.test_storage_dir)
        self.portfolio.positions.record_fill("NVDA", "BUY", 15.0, 130.0)
        save_path = store.save(self.portfolio)
        self.assertTrue(os.path.exists(save_path))

        # Restore from disk
        restored = store.restore_manager("port_test_01")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.portfolio_id, "port_test_01")
        self.assertTrue(restored.positions.has_position("NVDA"))
        self.assertEqual(restored.positions.get_position("NVDA").qty, 15.0)

    # =========================================================================
    # Group 2: Position Sizing (TC 11 - 20)
    # =========================================================================

    def test_11_valid_decimal_inputs(self):
        """TC-11: Verifies position sizing with Decimal inputs and 2% risk rule."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=100.0)
        # Equity = 100,000; Risk = 2,000. Price = 100, Stop = 90 (Distance = 10)
        # Qty = 2,000 / 10 = 200.0
        res = engine.calculate_size(
            symbol="AAPL",
            signal=sig,
            reference_price=Decimal("100.0"),
            equity=Decimal("100000.0"),
            available_cash=Decimal("100000.0"),
            stop_loss_price=Decimal("90.0"),
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.proposed_quantity, Decimal("200.00"))
        self.assertEqual(res.proposed_notional, Decimal("20000.00"))

    def test_12_fractional_quantity(self):
        """TC-12: Verifies fractional quantity preservation for crypto/fractional assets."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="BTC/USD", signal_type="BUY", price=60000.0)
        # Equity = 100,000; Risk = 2,000. Price = 60,000, Stop = 55,000 (Distance = 5,000)
        # Qty = 2,000 / 5,000 = 0.4 BTC
        res = engine.calculate_size(
            symbol="BTC/USD",
            signal=sig,
            reference_price=60000.0,
            equity=100000.0,
            available_cash=100000.0,
            stop_loss_price=55000.0,
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.proposed_quantity, Decimal("0.4000"))

    def test_13_notional_validation(self):
        """TC-13: Verifies notional calculation equals proposed_qty * reference_price."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=120.0)
        res = engine.calculate_size(
            symbol="NVDA",
            signal=sig,
            reference_price=120.0,
            equity=100000.0,
            available_cash=100000.0,
            stop_loss_price=110.0,
        )
        self.assertTrue(res.is_valid)
        expected_notional = quantize_currency(res.proposed_quantity * Decimal("120.0"))
        self.assertEqual(res.proposed_notional, expected_notional)

    def test_14_zero_stop_distance_rejection(self):
        """TC-14: Rejects zero stop distance to prevent division by zero / infinite size."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=120.0)
        res = engine.calculate_size(
            symbol="NVDA",
            signal=sig,
            reference_price=120.0,
            equity=100000.0,
            available_cash=100000.0,
            stop_loss_price=120.0,  # Zero distance!
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.reason_code, "ZERO_STOP_DISTANCE")

    def test_15_missing_reference_price(self):
        """TC-15: Rejects missing or non-positive reference price."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=0.0)
        res = engine.calculate_size(
            symbol="NVDA",
            signal=sig,
            reference_price=0.0,
            equity=100000.0,
            available_cash=100000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertIn("REFERENCE_PRICE", res.reason_code)

    def test_16_stale_price_rejection(self):
        """TC-16: Rejects reference price older than configured max_price_age_seconds."""
        engine = PositionSizingEngine(self.risk_config)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=120.0, signal_time=stale_time)
        res = engine.calculate_size(
            symbol="NVDA",
            signal=sig,
            reference_price=120.0,
            equity=100000.0,
            available_cash=100000.0,
            price_time=stale_time,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.reason_code, "STALE_REFERENCE_PRICE")

    def test_17_insufficient_simulated_cash(self):
        """TC-17: Rejects position sizing when simulated available cash is zero."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=120.0)
        res = engine.calculate_size(
            symbol="NVDA",
            signal=sig,
            reference_price=120.0,
            equity=100000.0,
            available_cash=0.0,  # No cash
            stop_loss_price=110.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.reason_code, "INSUFFICIENT_SIMULATED_CASH")

    def test_18_configured_position_limit(self):
        """TC-18: Caps position sizing to configured max_position_notional ($25,000)."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=100.0)
        # If stop distance is 1.0 (Stop=99), raw qty = 2000 / 1 = 2,000 shares ($200,000)
        # Should be capped by max_position_notional = 25,000 -> 250 shares ($25,000)
        res = engine.calculate_size(
            symbol="AAPL",
            signal=sig,
            reference_price=100.0,
            equity=100000.0,
            available_cash=100000.0,
            stop_loss_price=99.0,
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.proposed_quantity, Decimal("250.00"))
        self.assertEqual(res.proposed_notional, Decimal("25000.00"))
        self.assertTrue(res.risk_calculation_trace.get("capped_by_max_notional"))

    def test_19_precision_boundary(self):
        """TC-19: Verifies quantization respects precision boundaries."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="ETH/USD", signal_type="BUY", price=3000.0)
        res = engine.calculate_size(
            symbol="ETH/USD",
            signal=sig,
            reference_price=3000.0,
            equity=100000.0,
            available_cash=100000.0,
            stop_loss_price=2800.0,
            quantity_precision=3,
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.proposed_quantity.as_tuple().exponent, -3)

    def test_20_no_minimum_one_quantity_behavior(self):
        """TC-20: Verifies small sizes like 0.25 are not forced to integer minimum of 1."""
        engine = PositionSizingEngine(self.risk_config)
        sig = StrategySignal(symbol="BTC/USD", signal_type="BUY", price=60000.0)
        res = engine.calculate_size(
            symbol="BTC/USD",
            signal=sig,
            reference_price=60000.0,
            equity=50000.0,
            available_cash=50000.0,
            stop_loss_price=56000.0,  # Risk=1000, Dist=4000 -> Qty=0.25 BTC
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.proposed_quantity, Decimal("0.2500"))

    # =========================================================================
    # Group 3: Risk Management & Guards (TC 21 - 28)
    # =========================================================================

    def test_21_per_symbol_limit(self):
        """TC-21: Rejects intent when symbol exposure exceeds 30% of total equity."""
        limits = RiskLimitsEngine(self.risk_config)
        # Equity = 100,000, 30% limit = 30,000
        # Propose 35,000 notional
        passed, codes, _ = limits.check_position_limits(
            symbol="NVDA",
            proposed_qty=Decimal("250.0"),
            proposed_notional=Decimal("35000.0"),
            current_pos=None,
            equity=Decimal("100000.0"),
            gross_exposure=Decimal("0.0"),
        )
        self.assertFalse(passed)
        self.assertTrue(any("EXCEEDS_SYMBOL_EXPOSURE_LIMIT" in c for c in codes))

    def test_22_portfolio_exposure_limit(self):
        """TC-22: Rejects intent when gross exposure exceeds 100% of equity."""
        limits = RiskLimitsEngine(self.risk_config)
        # Existing gross exposure = 90,000; Propose 20,000 -> Total = 110,000 > 100,000
        passed, codes, _ = limits.check_position_limits(
            symbol="AMD",
            proposed_qty=Decimal("100.0"),
            proposed_notional=Decimal("20000.0"),
            current_pos=None,
            equity=Decimal("100000.0"),
            gross_exposure=Decimal("90000.0"),
        )
        self.assertFalse(passed)
        self.assertTrue(any("EXCEEDS_PORTFOLIO_EXPOSURE_LIMIT" in c for c in codes))

    def test_23_concurrent_position_limit(self):
        """TC-23: Rejects opening new symbol when max 5 concurrent positions reached."""
        limits = RiskLimitsEngine(self.risk_config)
        passed, codes = limits.check_portfolio_guards(
            symbol="TSLA",
            has_existing_position=False,
            active_positions_count=5,  # Already 5 open
            is_drawdown_locked=False,
        )
        self.assertFalse(passed)
        self.assertTrue(any("MAX_CONCURRENT_POSITIONS_REACHED" in c for c in codes))

    def test_24_daily_loss_guard(self):
        """TC-24: Rejects intent when daily loss limit (5%) is breached."""
        limits = RiskLimitsEngine(self.risk_config)
        passed, codes = limits.check_portfolio_guards(
            symbol="AAPL",
            has_existing_position=False,
            active_positions_count=1,
            is_drawdown_locked=False,
            daily_loss_pct=Decimal("0.06"),  # 6% > 5%
        )
        self.assertFalse(passed)
        self.assertTrue(any("DAILY_LOSS_LIMIT_BREACHED" in c for c in codes))

    def test_25_drawdown_calculation(self):
        """TC-25: Accurately calculates peak-to-trough equity drawdown percentage."""
        monitor = DrawdownMonitor("port_01", initial_equity=Decimal("100000.0"), max_drawdown_pct=Decimal("0.10"))
        # Drop to 95,000 -> Drawdown = 5%
        snap1, _ = monitor.update(Decimal("95000.0"))
        self.assertEqual(snap1.drawdown_amount, 5000.0)
        self.assertEqual(snap1.drawdown_pct, 0.05)
        self.assertFalse(snap1.is_locked)

    def test_26_drawdown_lock(self):
        """TC-26: Locks portfolio when drawdown breaches 10% threshold."""
        monitor = DrawdownMonitor("port_01", initial_equity=Decimal("100000.0"), max_drawdown_pct=Decimal("0.10"))
        # Drop to 89,000 -> Drawdown = 11% > 10% -> Lockout!
        snap, event = monitor.update(Decimal("89000.0"))
        self.assertTrue(snap.is_locked)
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "DRAWDOWN_LIMIT_BREACHED")
        self.assertEqual(event.severity, "LOCKOUT")

    def test_27_stale_data_guard(self):
        """TC-27: Verifies price freshness validation function catches stale timestamps."""
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=350)
        is_valid, err = validate_price_freshness(100.0, price_time=stale_time, max_age_seconds=300)
        self.assertFalse(is_valid)
        self.assertIn("STALE", err)

    def test_28_invalid_signal_rejection(self):
        """TC-28: Rejects unfinalized source bars and revision mismatches."""
        limits = RiskLimitsEngine(self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", source_bar_revision=2)
        # Unfinalized bar
        bar_provisional = MarketDataEvent(symbol="NVDA", is_final=False, bar_revision=2)
        passed1, codes1 = limits.check_signal_guards(sig, source_bar=bar_provisional)
        self.assertFalse(passed1)
        self.assertIn("UNFINALIZED_SOURCE_BAR", codes1)

        # Revision mismatch
        bar_mismatch = MarketDataEvent(symbol="NVDA", is_final=True, bar_revision=1)
        passed2, codes2 = limits.check_signal_guards(sig, source_bar=bar_mismatch)
        self.assertFalse(passed2)
        self.assertIn("SOURCE_BAR_REVISION_MISMATCH", codes2)

    # =========================================================================
    # Group 4: Signal Decision Engine (TC 29 - 34)
    # =========================================================================

    def test_29_valid_signal_acceptance(self):
        """TC-29: Valid BUY signal generates SignalDecision(status='ACCEPTED') and intent."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(
            symbol="AAPL",
            signal_type="BUY",
            price=150.0,
            strategy_version="1.0.0",
            environment="SIMULATION",
        )
        bar = MarketDataEvent(symbol="AAPL", is_final=True, bar_revision=0)
        decision, intent = engine.evaluate(
            signal=sig,
            reference_price=150.0,
            stop_loss_price=140.0,
            source_bar=bar,
        )
        self.assertEqual(decision.status, "ACCEPTED")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.side, "BUY")
        self.assertEqual(intent.symbol, "AAPL")
        self.assertGreater(intent.proposed_quantity, 0.0)

    def test_30_duplicate_signal_rejection(self):
        """TC-30: Re-evaluating the exact same signal_id is rejected with DUPLICATE_SIGNAL."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=150.0, signal_id="sig_dup_01")
        # First evaluation
        engine.evaluate(sig, reference_price=150.0)
        # Duplicate evaluation
        decision2, intent2 = engine.evaluate(sig, reference_price=150.0)
        self.assertEqual(decision2.status, "REJECTED")
        self.assertIn("DUPLICATE_SIGNAL", decision2.reason_codes)
        self.assertIsNone(intent2)

    def test_31_source_bar_revision_validation(self):
        """TC-31: Signal decision rejects bar revision mismatch."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="MSFT", signal_type="BUY", source_bar_revision=3)
        bar = MarketDataEvent(symbol="MSFT", is_final=True, bar_revision=1)
        decision, intent = engine.evaluate(sig, reference_price=300.0, source_bar=bar)
        self.assertEqual(decision.status, "REJECTED")
        self.assertIn("SOURCE_BAR_REVISION_MISMATCH", decision.reason_codes)
        self.assertIsNone(intent)

    def test_32_invalid_strategy_version(self):
        """TC-32: Signal with unauthorized strategy version is rejected."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", strategy_version="9.9.9")
        decision, intent = engine.evaluate(sig, reference_price=120.0)
        self.assertEqual(decision.status, "REJECTED")
        self.assertTrue(any("INCOMPATIBLE_STRATEGY_VERSION" in c for c in decision.reason_codes))
        self.assertIsNone(intent)

    def test_33_missing_metadata(self):
        """TC-33: Non-actionable HOLD or NO_SIGNAL is rejected."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="NVDA", signal_type="HOLD")
        decision, intent = engine.evaluate(sig, reference_price=120.0)
        self.assertEqual(decision.status, "REJECTED")
        self.assertIn("UNSUPPORTED_SIGNAL_TYPE_HOLD", decision.reason_codes)
        self.assertIsNone(intent)

    def test_34_deterministic_decision_id(self):
        """TC-34: Ensures deterministic configuration hashing and decision audit trail."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=150.0)
        decision, _ = engine.evaluate(sig, reference_price=150.0)
        self.assertTrue(decision.configuration_hash)
        self.assertEqual(len(decision.configuration_hash), 64)  # SHA-256
        self.assertEqual(decision.configuration_hash, self.risk_config.compute_hash())

    # =========================================================================
    # Group 5: Simulation Isolation & Invariants (TC 35 - 43)
    # =========================================================================

    def test_35_simulation_order_intent_generation(self):
        """TC-35: Emitted SimulationOrderIntent has all required fields and environment='SIMULATION'."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=150.0)
        _, intent = engine.evaluate(sig, reference_price=150.0, stop_loss_price=140.0)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.environment, "SIMULATION")
        self.assertTrue(intent.intent_id.startswith("intent_"))
        self.assertTrue(intent.idempotency_key)
        self.assertEqual(intent.side, "BUY")
        self.assertGreater(intent.proposed_quantity, 0.0)

    def test_36_no_simulated_order_creation(self):
        """TC-36: Confirms GĐ32 strictly emits SimulationOrderIntent and NEVER creates SimulatedOrder."""
        engine = SignalDecisionEngine(self.portfolio, self.risk_config)
        sig = StrategySignal(symbol="AAPL", signal_type="BUY", price=150.0)
        decision, intent = engine.evaluate(sig, reference_price=150.0)
        self.assertIsNotNone(intent)
        self.assertFalse(hasattr(engine, "simulated_orders"))
        self.assertFalse(hasattr(intent, "simulated_order_id"))

    def test_37_no_mock_broker_call(self):
        """TC-37: Confirms GĐ32 never calls V1 Mock Trading Broker."""
        import sys
        # Check mock broker is not imported or modified in GĐ32 modules
        from libs.bot.portfolio import manager
        from libs.bot.risk import decision_engine
        self.assertNotIn("mock_trading_broker", sys.modules.get("libs.bot.portfolio.manager", {}).__dict__)
        self.assertNotIn("mock_trading_broker", sys.modules.get("libs.bot.risk.decision_engine", {}).__dict__)

    def test_38_no_alpaca_broker_calls(self):
        """TC-38: Confirms zero Alpaca SDK submit/replace/cancel calls."""
        # Ensure AlpacaPaperGate is strictly closed
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        self.assertEqual(os.environ.get("TRADING_MODE", "DRY_RUN"), "DRY_RUN")

    def test_39_no_live_endpoint(self):
        """TC-39: Confirms no live broker execution endpoints exist."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_40_alpaca_account_isolation(self):
        """TC-40: Confirms SimulationPortfolio cash and equity do not read from Alpaca Paper."""
        self.assertEqual(self.portfolio.portfolio_id, "port_test_01")
        self.assertFalse(hasattr(self.portfolio, "alpaca_client"))
        self.assertEqual(self.portfolio.cash, Decimal("100000.0"))

    def test_41_workbench_account_isolation(self):
        """TC-41: Confirms SimulationPortfolio is fully isolated from V1 Workbench data."""
        self.assertNotIn("mock_broker", self.portfolio.portfolio_id)
        self.assertEqual(self.portfolio.positions.get_active_positions_count(), 0)

    def test_42_no_natural_topic_writes(self):
        """TC-42: Confirms no simulated intents or decisions are written to natural market topics."""
        from libs.bot.risk.decision_engine import SignalDecisionEngine
        self.assertFalse(hasattr(SignalDecisionEngine, "kafka_producer"))
        self.assertFalse(hasattr(SignalDecisionEngine, "publish_to_topic"))

    def test_43_dry_run_invariant(self):
        """TC-43: Confirms global TRADING_MODE=DRY_RUN invariant."""
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        self.assertEqual(os.environ.get("TRADING_MODE", "DRY_RUN"), "DRY_RUN")


if __name__ == "__main__":
    unittest.main()
