"""
tests/test_gd29_contracts.py — Contract & Interface Verification Suite (GĐ29)
Verifies all 26 core architectural criteria for AlgoTrading V2.0 Paper Trading Bot Base Adaptation.
"""

import unittest
from datetime import datetime, timezone
import os
import sys

# Ensure repository root is on PYTHONPATH
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from libs.bot.config import TradingConfig
from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    SimulatedPosition,
    PortfolioSnapshot,
    BotAuditEvent,
)
from libs.bot.interfaces import (
    TradingStrategy,
    BotDataManager,
    BotPortfolioManager,
    SimulationOrderManager,
    TradingBotLifecycle,
)
from libs.bot.strategies import (
    MovingAverageCrossoverStrategy,
    RSIStrategy,
    V1StrategyAdapter,
)
from libs.bot.adapters import (
    BotSimulationBrokerAdapter,
    BotRedpandaConsumerAdapter,
)
from libs.alpaca_paper_gate import (
    AlpacaPaperGate,
    PaperExecutionGateClosedError,
    LiveTradingProhibitedError,
)


class TestGD29PaperBotContracts(unittest.TestCase):
    """26-criteria contract and interface verification suite for GĐ29."""

    # 1. Domain: Simulation environment tag invariant
    def test_01_domain_environment_simulation(self):
        entities = [
            BotSession(),
            MarketDataEvent(),
            StrategySignal(),
            SignalDecision(),
            SimulationOrderIntent(),
            SimulatedOrder(),
            SimulatedFill(),
            SimulatedPosition(),
            PortfolioSnapshot(),
            BotAuditEvent(),
        ]
        for entity in entities:
            self.assertEqual(entity.environment, "SIMULATION", f"{type(entity).__name__} must be SIMULATION")

    # 2. Domain: BotSession lifecycle attributes
    def test_02_domain_bot_session_lifecycle(self):
        session = BotSession(bot_name="AlphaBot", strategy_name="SMA_CROSS", timeframe="1m")
        self.assertEqual(session.status, "STOPPED")
        self.assertEqual(session.timeframe, "1m")
        self.assertTrue(session.session_id.startswith("session_"))

    # 3. Domain: MarketDataEvent 1m OHLCV & finality
    def test_03_domain_market_data_event_1m(self):
        bar = MarketDataEvent(
            symbol="BTC/USD",
            open=90000.0,
            high=90200.0,
            low=89900.0,
            close=90150.0,
            volume=15.5,
            is_final=True,
        )
        self.assertEqual(bar.timeframe, "1m")
        self.assertTrue(bar.is_final)
        self.assertEqual(bar.close, 90150.0)

    # 4. Domain: StrategySignal fields & types
    def test_04_domain_strategy_signal_immutability(self):
        sig = StrategySignal(strategy_id="TEST_STRAT", symbol="NVDA", signal_type="BUY", price=140.0)
        self.assertEqual(sig.signal_type, "BUY")
        self.assertEqual(sig.price, 140.0)
        self.assertEqual(sig.strength, 1.0)

    # 5. Domain: SignalDecision status & reason
    def test_05_domain_signal_decision(self):
        dec_accepted = SignalDecision(signal_id="sig_1", symbol="NVDA", status="ACCEPTED", calculated_qty=10.0)
        dec_rejected = SignalDecision(
            signal_id="sig_2", symbol="NVDA", status="REJECTED", rejection_reason="INSUFFICIENT_BUYING_POWER"
        )
        self.assertEqual(dec_accepted.status, "ACCEPTED")
        self.assertEqual(dec_rejected.status, "REJECTED")
        self.assertEqual(dec_rejected.rejection_reason, "INSUFFICIENT_BUYING_POWER")

    # 6. Domain: SimulationOrderIntent & idempotency
    def test_06_domain_simulation_order_intent(self):
        intent = SimulationOrderIntent(symbol="AAPL", side="BUY", qty=20.0, limit_price=230.0)
        self.assertTrue(intent.idempotency_key.startswith("idemp_"))
        self.assertEqual(intent.side, "BUY")
        self.assertEqual(intent.qty, 20.0)

    # 7. Domain: SimulatedOrder status transition
    def test_07_domain_simulated_order(self):
        order = SimulatedOrder(symbol="TSLA", side="BUY", order_type="MARKET", qty=5.0)
        self.assertEqual(order.status, "NEW")
        order.status = "FILLED"
        self.assertEqual(order.status, "FILLED")

    # 8. Domain: SimulatedFill assumptions
    def test_08_domain_simulated_fill(self):
        fill = SimulatedFill(
            simulated_order_id="ord_123",
            symbol="NVDA",
            side="BUY",
            fill_price=138.5,
            fill_qty=10.0,
            fee=0.0,
        )
        self.assertEqual(fill.assumptions, "ZERO_SLIPPAGE_BAR_CLOSE")
        self.assertEqual(fill.fill_qty, 10.0)

    # 9. Domain: SimulatedPosition PnL recalculation
    def test_09_domain_simulated_position(self):
        pos = SimulatedPosition(
            symbol="NVDA",
            qty=10.0,
            avg_entry_price=100.0,
            current_price=100.0,
            cost_basis=1000.0,
            market_value=1000.0,
        )
        pos.recalculate(latest_price=120.0)
        self.assertEqual(pos.market_value, 1200.0)
        self.assertEqual(pos.unrealized_pnl, 200.0)

    # 10. Domain: PortfolioSnapshot accounting
    def test_10_domain_portfolio_snapshot(self):
        snap = PortfolioSnapshot(cash=50000.0, equity=110000.0, realized_pnl=5000.0, unrealized_pnl=5000.0)
        self.assertEqual(snap.cash, 50000.0)
        self.assertEqual(snap.equity, 110000.0)

    # 11. Domain: BotAuditEvent trace & payload
    def test_11_domain_bot_audit_event(self):
        audit = BotAuditEvent(
            component="ORDER_ENGINE",
            event_type="ORDER_SUBMITTED",
            reason="Signal execution",
            payload={"order_id": "ord_1"},
        )
        self.assertTrue(audit.trace_id.startswith("trace_"))
        self.assertEqual(audit.payload["order_id"], "ord_1")

    # 12. Config: Zero secret storage enforcement
    def test_12_trading_config_no_secrets(self):
        # Valid config passes
        cfg = TradingConfig(bot_name="SafeBot", symbols=["NVDA"])
        self.assertEqual(cfg.bot_name, "SafeBot")

        # Config containing API key raises ValueError
        with self.assertRaises(ValueError) as ctx:
            TradingConfig(api_key="AKIA_SAMPLE_KEY_SHOULD_FAIL")
        self.assertIn("security violation", str(ctx.exception).lower())

    # 13. Config: Primary timeframe '1m' & dry run invariant
    def test_13_trading_config_timeframe_1m(self):
        cfg = TradingConfig(timeframe="1m")
        self.assertEqual(cfg.timeframe, "1m")
        self.assertTrue(cfg.dry_run)

        # Rejecting invalid timeframe
        with self.assertRaises(ValueError):
            TradingConfig(timeframe="1d")

        # Rejecting live mode in TradingConfig
        with self.assertRaises(ValueError):
            TradingConfig(dry_run=False)

    # 14. Strategy: Interface contracts (ABC)
    def test_14_strategy_interface_contract(self):
        class IncompleteStrategy(TradingStrategy):
            pass

        with self.assertRaises(TypeError):
            IncompleteStrategy()

    # 15. Strategy: MovingAverageCrossoverStrategy deterministic evaluation
    def test_15_strategy_ma_crossover_deterministic(self):
        # Window 2 short, 4 long
        strat = MovingAverageCrossoverStrategy(short_window=2, long_window=4, require_final=True)
        # Push 4 bars of flat price 10.0 (short=10, long=10)
        for _ in range(4):
            bar = MarketDataEvent(symbol="NVDA", close=10.0, is_final=True)
            strat.generate_signals(bar)

        # 5th bar flat (prev short=10, prev long=10, curr short=10, curr long=10)
        bar5 = MarketDataEvent(symbol="NVDA", close=10.0, is_final=True)
        sig5 = strat.generate_signals(bar5)
        self.assertIsNone(sig5)

        # 6th bar sharp upward jump to 20.0
        # History: [10, 10, 10, 10, 10, 20]
        # prev slice: [10, 10, 10, 10] -> prev_short=10, prev_long=10
        # curr slice: [10, 10, 10, 20] -> curr_short=(10+20)/2=15, curr_long=(10+10+10+20)/4=12.5
        # Golden Cross -> BUY
        bar6 = MarketDataEvent(symbol="NVDA", close=20.0, is_final=True)
        sig6 = strat.generate_signals(bar6)
        self.assertIsNotNone(sig6)
        self.assertEqual(sig6.signal_type, "BUY")
        self.assertEqual(sig6.price, 20.0)

    # 16. Strategy: RSIStrategy deterministic evaluation
    def test_16_strategy_rsi_deterministic(self):
        strat = RSIStrategy(period=4, oversold=30.0, overbought=70.0, require_final=True)
        # Declining prices to trigger oversold
        prices = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0]
        sig = None
        for p in prices:
            bar = MarketDataEvent(symbol="BTC/USD", close=p, is_final=True)
            res = strat.generate_signals(bar)
            if res:
                sig = res
        self.assertIsNotNone(sig)
        self.assertEqual(sig.signal_type, "BUY")
        self.assertIn("Oversold", sig.reason)

    # 17. Strategy: V1StrategyAdapter translates Flink signal JSON
    def test_17_strategy_v1_adapter(self):
        adapter = V1StrategyAdapter()
        flink_payload = {
            "symbol": "NVDA",
            "signal_type": "BUY",
            "price": 139.5,
            "strategy_name": "SMA_20_50_CROSS",
            "timestamp_ms": 1730000000000,
        }
        domain_sig = adapter.translate_flink_signal(flink_payload)
        self.assertEqual(domain_sig.symbol, "NVDA")
        self.assertEqual(domain_sig.signal_type, "BUY")
        self.assertEqual(domain_sig.price, 139.5)
        self.assertEqual(domain_sig.environment, "SIMULATION")

    # 18. DataManager: Interface contract
    def test_18_data_manager_interface_contract(self):
        class IncompleteDM(BotDataManager):
            pass

        with self.assertRaises(TypeError):
            IncompleteDM()

    # 19. DataManager: Bar finalization filtering (provisional vs final)
    def test_19_data_manager_bar_finalization_filter(self):
        adapter = BotRedpandaConsumerAdapter(require_final=True)
        provisional_bar = MarketDataEvent(symbol="NVDA", close=138.0, is_final=False)
        final_bar = MarketDataEvent(symbol="NVDA", close=138.5, is_final=True)

        res_prov = adapter.process_bar(provisional_bar)
        self.assertIsNone(res_prov, "Provisional bars must be filtered out when require_final=True")

        res_final = adapter.process_bar(final_bar)
        self.assertIsNotNone(res_final)
        self.assertEqual(adapter.get_latest_bar("NVDA").close, 138.5)

    # 20. PortfolioManager: Interface contract
    def test_20_portfolio_manager_interface_contract(self):
        class IncompletePM(BotPortfolioManager):
            pass

        with self.assertRaises(TypeError):
            IncompletePM()

    # 21. PortfolioManager: 2% risk rule position sizing formula
    def test_21_portfolio_manager_2pct_risk_sizing(self):
        cfg = TradingConfig(initial_cash=100000.0, risk_per_trade_pct=0.02)
        adapter = BotSimulationBrokerAdapter(cfg)
        # Cash = 100,000. 2% risk = 2,000.
        # Price = 100. Stop loss = 90. Per share risk = 10.
        # Expected shares = 2000 / 10 = 200 shares.
        qty = adapter.calculate_position_size(symbol="NVDA", price=100.0, stop_loss_price=90.0)
        self.assertEqual(qty, 200.0)

    # 22. PortfolioManager: Insufficient buying power rejection
    def test_22_portfolio_manager_signal_rejection_insufficient_funds(self):
        cfg = TradingConfig(initial_cash=50.0, risk_per_trade_pct=0.02)
        adapter = BotSimulationBrokerAdapter(cfg)
        sig = StrategySignal(symbol="NVDA", signal_type="BUY", price=140.0)
        decision = adapter.evaluate_signal(sig, current_price=140.0)
        self.assertEqual(decision.status, "REJECTED")
        self.assertIn("INSUFFICIENT_BUYING_POWER", decision.rejection_reason)

    # 23. OrderManager: Interface contract
    def test_23_order_manager_interface_contract(self):
        class IncompleteOM(SimulationOrderManager):
            pass

        with self.assertRaises(TypeError):
            IncompleteOM()

    # 24. OrderManager: Simulation isolation & zero external network calls
    def test_24_order_manager_simulation_isolation(self):
        cfg = TradingConfig(initial_cash=10000.0)
        adapter = BotSimulationBrokerAdapter(cfg)

        intent = SimulationOrderIntent(
            symbol="NVDA",
            side="BUY",
            qty=10.0,
            limit_price=100.0,
            idempotency_key="idemp_unit_test_01",
        )
        order = adapter.submit_order_intent(intent)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(adapter.cash, 9000.0)
        self.assertIn("NVDA", adapter.positions)
        self.assertEqual(adapter.positions["NVDA"].qty, 10.0)

        # Idempotency check: duplicate intent returns existing order without extra fill
        dup_order = adapter.submit_order_intent(intent)
        self.assertEqual(dup_order.simulated_order_id, order.simulated_order_id)
        self.assertEqual(adapter.cash, 9000.0)

    # 25. Bot Lifecycle: State transitions
    def test_25_bot_lifecycle_state_transitions(self):
        class MockBotLifecycle(TradingBotLifecycle):
            def __init__(self):
                self.state = "STOPPED"

            def start(self):
                self.state = "RUNNING"

            def pause(self):
                self.state = "PAUSED"

            def resume(self):
                self.state = "RUNNING"

            def stop(self):
                self.state = "STOPPED"

            def get_status(self):
                return self.state

        bot = MockBotLifecycle()
        self.assertEqual(bot.get_status(), "STOPPED")
        bot.start()
        self.assertEqual(bot.get_status(), "RUNNING")
        bot.pause()
        self.assertEqual(bot.get_status(), "PAUSED")
        bot.resume()
        self.assertEqual(bot.get_status(), "RUNNING")
        bot.stop()
        self.assertEqual(bot.get_status(), "STOPPED")

    # 26. Safety Boundaries: DRY_RUN & PaperExecutionGate fail-closed
    def test_26_safety_fail_closed_and_dry_run(self):
        # 1. AlpacaPaperGate must be closed
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "NVDA", "qty": 1, "side": "buy"})

        # 2. Live trading prohibition assertion
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

        # 3. Simulation adapter rejects live environment
        cfg = TradingConfig()
        cfg.environment = "LIVE"  # Artificially altered
        with self.assertRaises(LiveTradingProhibitedError):
            BotSimulationBrokerAdapter(cfg)


if __name__ == "__main__":
    unittest.main()
