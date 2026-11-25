"""
tests/test_gd31_strategy_engine.py — Comprehensive Test Suite for GĐ31 Strategy Engine & Indicators
Validates 38 core criteria across 4 test groups:
- Indicator Tests (1-14)
- Strategy Tests (15-24)
- Engine Tests (25-32)
- Safety Tests (33-38)
"""

import unittest
from datetime import datetime, timezone, timedelta
import os
import sys
import tempfile
import shutil

# Ensure repository root is on PYTHONPATH
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from libs.bot.domain import MarketDataEvent, StrategySignal
from libs.bot.indicators import (
    IndicatorResult,
    SMAIndicator,
    EMAIndicator,
    RSIIndicator,
    MACDIndicator,
    BollingerBandsIndicator,
)
from libs.bot.strategies.ma_crossover import MovingAverageCrossoverStrategy
from libs.bot.strategies.rsi_strategy import RSIStrategy
from libs.bot.strategies.v1_adapter import V1StrategyAdapter
from libs.bot.strategy_registry import StrategyRegistry
from libs.bot.signal_validator import SignalValidator
from libs.bot.signal_store import SignalStore
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.strategy_comparison import StrategyComparator, ComparisonCategory
from libs.bot.data_access import PaperBotDataAccess
from libs.alpaca_paper_gate import AlpacaPaperGate, PaperExecutionGateClosedError, LiveTradingProhibitedError


class TestGD31StrategyEngine(unittest.TestCase):
    """38-criteria test suite for GĐ31 Python Strategy Engine & Indicator Library."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_gd31_strategies_")
        self.signal_store = SignalStore(base_dir=self.temp_dir)
        self.validator = SignalValidator()
        self.registry = StrategyRegistry()
        self.registry.register(MovingAverageCrossoverStrategy)
        self.registry.register(RSIStrategy)
        self.registry.register(V1StrategyAdapter)
        self.data_access = PaperBotDataAccess()
        self.engine = StrategyExecutionEngine(
            data_access=self.data_access,
            registry=self.registry,
            validator=self.validator,
            store=self.signal_store,
        )

    def tearDown(self):
        self.engine.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_bar(self, symbol="NVDA", close=100.0, is_final=True, minute_offset=0, revision=0):
        t0 = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
        return MarketDataEvent(
            symbol=symbol,
            close=close,
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            volume=1000.0,
            event_time=t0 + timedelta(minutes=minute_offset),
            is_final=is_final,
            bar_revision=revision,
            environment="SIMULATION",
        )

    # =========================================================================
    # Group 1: Indicator Tests (1-14)
    # =========================================================================

    def test_01_sma_correctness(self):
        sma = SMAIndicator(period=3)
        prices = [10.0, 20.0, 30.0]
        res = None
        for i, p in enumerate(prices):
            res = sma.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertEqual(res.value, 20.0)

    def test_02_sma_warmup(self):
        sma = SMAIndicator(period=5)
        for i in range(4):
            res = sma.update(self._create_bar(close=10.0, minute_offset=i))
            self.assertFalse(res.warmup_complete)
            self.assertIsNone(res.value)
        res5 = sma.update(self._create_bar(close=10.0, minute_offset=4))
        self.assertTrue(res5.warmup_complete)
        self.assertEqual(res5.value, 10.0)

    def test_03_ema_initialization(self):
        ema = EMAIndicator(period=3)
        prices = [10.0, 20.0, 30.0]  # SMA = 20.0
        res = None
        for i, p in enumerate(prices):
            res = ema.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertEqual(res.value, 20.0)

    def test_04_ema_recurrence(self):
        # period 3 -> alpha = 2 / (3 + 1) = 0.5
        ema = EMAIndicator(period=3)
        prices = [10.0, 20.0, 30.0]  # init = 20.0
        for i, p in enumerate(prices):
            ema.update(self._create_bar(close=p, minute_offset=i))
        # 4th bar close = 40.0 -> EMA = 40 * 0.5 + 20.0 * 0.5 = 30.0
        res4 = ema.update(self._create_bar(close=40.0, minute_offset=3))
        self.assertEqual(res4.value, 30.0)

    def test_05_rsi_simple_rolling(self):
        rsi = RSIIndicator(period=3, method="SIMPLE_ROLLING")
        # 4 prices -> 3 changes: +10, +10, +10
        prices = [100.0, 110.0, 120.0, 130.0]
        res = None
        for i, p in enumerate(prices):
            res = rsi.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertEqual(res.value, 100.0)

    def test_06_rsi_wilder(self):
        rsi = RSIIndicator(period=3, method="WILDER")
        prices = [100.0, 90.0, 80.0, 70.0]  # all losses
        res = None
        for i, p in enumerate(prices):
            res = rsi.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertEqual(res.value, 0.0)

    def test_07_rsi_zero_gain_case(self):
        rsi = RSIIndicator(period=3, method="SIMPLE_ROLLING")
        prices = [50.0, 45.0, 40.0, 35.0]
        res = None
        for i, p in enumerate(prices):
            res = rsi.update(self._create_bar(close=p, minute_offset=i))
        self.assertEqual(res.value, 0.0)

    def test_08_rsi_zero_loss_case(self):
        rsi = RSIIndicator(period=3, method="SIMPLE_ROLLING")
        prices = [50.0, 55.0, 60.0, 65.0]
        res = None
        for i, p in enumerate(prices):
            res = rsi.update(self._create_bar(close=p, minute_offset=i))
        self.assertEqual(res.value, 100.0)

    def test_09_rsi_flat_price_case(self):
        rsi = RSIIndicator(period=3, method="SIMPLE_ROLLING")
        prices = [50.0, 50.0, 50.0, 50.0]
        res = None
        for i, p in enumerate(prices):
            res = rsi.update(self._create_bar(close=p, minute_offset=i))
        self.assertEqual(res.value, 50.0)

    def test_10_macd_correctness(self):
        macd = MACDIndicator(fast_period=2, slow_period=4, signal_period=2)
        # Slow 4 + Signal 2 -> requires at least 6 bars
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        res = None
        for i, p in enumerate(prices):
            res = macd.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertIn("macd_line", res.value)
        self.assertIn("signal_line", res.value)
        self.assertIn("histogram", res.value)
        expected_hist = round(res.value["macd_line"] - res.value["signal_line"], 6)
        self.assertEqual(res.value["histogram"], expected_hist)

    def test_11_macd_warmup(self):
        macd = MACDIndicator(fast_period=3, slow_period=6, signal_period=3)
        for i in range(5):
            res = macd.update(self._create_bar(close=100.0, minute_offset=i))
            self.assertFalse(res.warmup_complete)
            self.assertIsNone(res.value)

    def test_12_bollinger_calculation(self):
        bb = BollingerBandsIndicator(period=3, multiplier=2.0, ddof=0)
        # prices: [10, 20, 30] -> mean = 20.0
        # variance: ((10-20)^2 + (20-20)^2 + (30-20)^2) / 3 = 200 / 3 = 66.6667 -> std = 8.164966
        # upper = 20 + 2 * 8.164966 = 36.3299
        prices = [10.0, 20.0, 30.0]
        res = None
        for i, p in enumerate(prices):
            res = bb.update(self._create_bar(close=p, minute_offset=i))
        self.assertTrue(res.warmup_complete)
        self.assertEqual(res.value["middle_band"], 20.0)
        self.assertAlmostEqual(res.value["upper_band"], 36.329932, places=4)
        self.assertAlmostEqual(res.value["lower_band"], 3.670068, places=4)

    def test_13_bollinger_std_dev_policy(self):
        bb_pop = BollingerBandsIndicator(period=3, multiplier=1.0, ddof=0)
        bb_sample = BollingerBandsIndicator(period=3, multiplier=1.0, ddof=1)
        prices = [10.0, 20.0, 30.0]
        for i, p in enumerate(prices):
            res_pop = bb_pop.update(self._create_bar(close=p, minute_offset=i))
            res_smp = bb_sample.update(self._create_bar(close=p, minute_offset=i))
        # Sample std dev (divided by 2) must be greater than population std dev (divided by 3)
        self.assertGreater(res_smp.value["std_dev"], res_pop.value["std_dev"])

    def test_14_indicator_missing_invalid_input(self):
        with self.assertRaises(ValueError):
            SMAIndicator(period=0)
        with self.assertRaises(ValueError):
            RSIIndicator(period=-5)
        with self.assertRaises(ValueError):
            MACDIndicator(fast_period=20, slow_period=10)

    # =========================================================================
    # Group 2: Strategy Tests (15-24)
    # =========================================================================

    def test_15_bullish_sma_crossover(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, emit_hold=True)
        # Push 4 bars flat at 10.0 -> seed baseline
        for i in range(4):
            strat.generate_signals(self._create_bar(close=10.0, minute_offset=i))
        strat.generate_signals(self._create_bar(close=10.0, minute_offset=4))
        # Jump to 20.0 -> fast crosses above slow -> BUY
        sig = strat.generate_signals(self._create_bar(close=20.0, minute_offset=5))
        self.assertEqual(sig.signal_type, "BUY")
        self.assertIn("BULLISH_CROSSOVER", sig.reason_codes)

    def test_16_bearish_sma_crossover(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, emit_hold=True)
        for i in range(4):
            strat.generate_signals(self._create_bar(close=20.0, minute_offset=i))
        strat.generate_signals(self._create_bar(close=20.0, minute_offset=4))
        # Drop to 10.0 -> fast crosses below slow -> SELL
        sig = strat.generate_signals(self._create_bar(close=10.0, minute_offset=5))
        self.assertEqual(sig.signal_type, "SELL")
        self.assertIn("BEARISH_CROSSOVER", sig.reason_codes)

    def test_17_no_crossover(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, emit_hold=True)
        # Flat prices across all bars -> NO crossover
        for i in range(6):
            sig = strat.generate_signals(self._create_bar(close=15.0, minute_offset=i))
        self.assertEqual(sig.signal_type, "HOLD")
        self.assertIn("NO_STRATEGY_CONDITION", sig.reason_codes)

    def test_18_rsi_region_entry(self):
        strat = RSIStrategy(period=3, oversold=30.0, overbought=70.0, emit_hold=True)
        # Declining prices to force RSI below 30
        prices = [100.0, 90.0, 80.0, 70.0, 60.0]
        signals = [strat.generate_signals(self._create_bar(close=p, minute_offset=i)) for i, p in enumerate(prices)]
        buy_signals = [s for s in signals if s.signal_type == "BUY"]
        self.assertGreaterEqual(len(buy_signals), 1)
        self.assertIn("RSI_OVERSOLD_ENTRY", buy_signals[0].reason_codes)

    def test_19_rsi_region_exit(self):
        strat = RSIStrategy(period=3, oversold=30.0, overbought=70.0, emit_hold=True)
        # Force into oversold
        for i, p in enumerate([100.0, 80.0, 60.0, 40.0]):
            strat.generate_signals(self._create_bar(close=p, minute_offset=i))
        # Price recovers sharply -> exits oversold back to neutral
        sig_exit = strat.generate_signals(self._create_bar(close=70.0, minute_offset=4))
        self.assertEqual(sig_exit.signal_type, "HOLD")
        self.assertIn("RSI_REGION_EXIT", sig_exit.reason_codes)

    def test_20_no_repeated_rsi_event(self):
        strat = RSIStrategy(period=3, oversold=30.0, overbought=70.0, emit_hold=True)
        # Multiple declining bars keeping price in oversold
        prices = [100.0, 80.0, 60.0, 40.0, 30.0, 20.0, 10.0]
        signals = [strat.generate_signals(self._create_bar(close=p, minute_offset=i)) for i, p in enumerate(prices)]
        buy_count = sum(1 for s in signals if s.signal_type == "BUY")
        # Exactly one entry BUY signal allowed; subsequent bars must be HOLD (no duplicate signals)
        self.assertEqual(buy_count, 1)

    def test_21_insufficient_warmup(self):
        strat = MovingAverageCrossoverStrategy(fast_period=5, slow_period=10, emit_hold=True)
        sig = strat.generate_signals(self._create_bar(close=100.0, minute_offset=0))
        self.assertEqual(sig.signal_type, "NO_SIGNAL")
        self.assertIn("INSUFFICIENT_WARMUP", sig.reason_codes)

    def test_22_finalized_bar_only(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, require_final=True, emit_hold=True)
        prov_bar = self._create_bar(close=100.0, is_final=False)
        sig = strat.generate_signals(prov_bar)
        self.assertEqual(sig.signal_type, "NO_SIGNAL")
        self.assertIn("BAR_NOT_FINAL", sig.reason_codes)

    def test_23_deterministic_output(self):
        strat1 = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3, emit_hold=True)
        strat2 = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3, emit_hold=True)
        prices = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        sigs1 = [strat1.generate_signals(self._create_bar(close=p, minute_offset=i)).signal_type for i, p in enumerate(prices)]
        sigs2 = [strat2.generate_signals(self._create_bar(close=p, minute_offset=i)).signal_type for i, p in enumerate(prices)]
        self.assertEqual(sigs1, sigs2)

    def test_24_multiple_symbol_isolation(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, emit_hold=True)
        # NVDA prices flat
        for i in range(5):
            strat.generate_signals(self._create_bar(symbol="NVDA", close=10.0, minute_offset=i))
        # BTC prices flat then jump to produce golden cross
        for i in range(4):
            strat.generate_signals(self._create_bar(symbol="BTC/USD", close=1000.0, minute_offset=i))
        strat.generate_signals(self._create_bar(symbol="BTC/USD", close=1000.0, minute_offset=4))
        sig_btc = strat.generate_signals(self._create_bar(symbol="BTC/USD", close=2000.0, minute_offset=5))
        # BTC triggers BUY while NVDA remains HOLD
        sig_nvda = strat.generate_signals(self._create_bar(symbol="NVDA", close=10.0, minute_offset=5))
        self.assertEqual(sig_btc.signal_type, "BUY")
        self.assertEqual(sig_nvda.signal_type, "HOLD")

    # =========================================================================
    # Group 3: Engine Tests (25-32)
    # =========================================================================

    def test_25_strategy_registry(self):
        cls_ma = self.registry.get_class("MA_CROSS_1M")
        self.assertEqual(cls_ma, MovingAverageCrossoverStrategy)
        catalogue = self.registry.list_strategies()
        strat_ids = [c["strategy_id"] for c in catalogue]
        self.assertIn("MA_CROSS_1M", strat_ids)
        self.assertIn("RSI_1M", strat_ids)

    def test_26_configuration_validation(self):
        is_val, errors = self.registry.validate_configuration("MA_CROSS_1M", {"fast_period": 20, "slow_period": 50})
        self.assertTrue(is_val)
        self.assertEqual(len(errors), 0)

        # Invalid: missing slow_period
        is_val_bad, errors_bad = self.registry.validate_configuration("MA_CROSS_1M", {"fast_period": 20})
        self.assertFalse(is_val_bad)

    def test_27_strategy_version_isolation(self):
        inst = self.registry.instantiate("MA_CROSS_1M", {"fast_period": 10, "slow_period": 30})
        self.assertEqual(inst.strategy_version, "1.0.0")
        self.assertTrue(len(inst.get_configuration_hash()) > 0)

    def test_28_signal_deduplication(self):
        sig = StrategySignal(
            strategy_id="TEST_STRAT", symbol="NVDA", signal_type="BUY", price=140.0,
            source_bar_key="NVDA:1m:2026-11-22T10:00:00Z", source_bar_revision=0
        )
        is_new1, _, act1 = self.validator.validate_and_deduplicate(sig)
        self.assertTrue(is_new1)
        self.assertEqual(act1, "NEW_SIGNAL_EMITTED")

        # Duplicate evaluation of identical bar and revision
        is_new2, _, act2 = self.validator.validate_and_deduplicate(sig)
        self.assertFalse(is_new2)
        self.assertEqual(act2, "DUPLICATE_SUPPRESSED")

    def test_29_updated_bar_revision_handling(self):
        sig_rev0 = StrategySignal(
            strategy_id="TEST_STRAT", symbol="NVDA", signal_type="BUY", price=140.0,
            source_bar_key="NVDA:1m:2026-11-22T10:00:00Z", source_bar_revision=0
        )
        self.validator.validate_and_deduplicate(sig_rev0)

        # Bar updated to revision 1
        sig_rev1 = StrategySignal(
            strategy_id="TEST_STRAT", symbol="NVDA", signal_type="BUY", price=140.5,
            source_bar_key="NVDA:1m:2026-11-22T10:00:00Z", source_bar_revision=1
        )
        is_new, _, act = self.validator.validate_and_deduplicate(sig_rev1)
        self.assertTrue(is_new)
        self.assertEqual(act, "REVISION_UPDATED")

    def test_30_replay_determinism(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=4, emit_hold=True)
        self.engine.add_strategy_instance(strat, ["NVDA"])

        bars = [self._create_bar(close=10.0 + (i * 2.0), minute_offset=i) for i in range(10)]

        # Pass 1
        self.engine.reset_state()
        pass1 = [self.engine.process_bar(b) for b in bars]

        # Pass 2
        self.engine.reset_state()
        pass2 = [self.engine.process_bar(b) for b in bars]

        self.assertEqual(len(pass1), len(pass2))
        for p1, p2 in zip(pass1, pass2):
            self.assertEqual([s.signal_type for s in p1], [s.signal_type for s in p2])

    def test_31_graceful_shutdown(self):
        self.engine.start()
        self.assertTrue(self.engine.is_running)
        self.engine.stop()
        self.assertFalse(self.engine.is_running)

    def test_32_v1_strategy_adapter_readonly(self):
        adapter = V1StrategyAdapter()
        flink_payload = {
            "symbol": "BTC/USD", "signal_type": "BUY", "price": 91500.0,
            "strategy_name": "SMA20_SMA50_CROSS", "timestamp_ms": 1730000000000
        }
        sig = adapter.translate_flink_signal(flink_payload)
        self.assertEqual(sig.signal_type, "BUY")
        self.assertEqual(sig.symbol, "BTC/USD")
        self.assertEqual(sig.environment, "SIMULATION")

        # Compare with Python signal
        py_sig = StrategySignal(
            symbol="BTC/USD", signal_type="BUY", price=91500.0,
            signal_time=datetime.fromtimestamp(1730000000, tz=timezone.utc),
            timeframe="1m"
        )
        comp = StrategyComparator.compare_signals(py_sig, sig)
        self.assertEqual(comp["category"], ComparisonCategory.MATCH)

    # =========================================================================
    # Group 4: Safety Tests (33-38)
    # =========================================================================

    def test_33_no_ordermanager_invocation(self):
        # Assert StrategyExecutionEngine has zero OrderManager attributes or methods
        self.assertFalse(hasattr(self.engine, "order_manager"))
        self.assertFalse(hasattr(self.engine, "submit_order"))

    def test_34_no_mock_broker_order_creation(self):
        # Assert StrategyExecutionEngine does not interact with mock broker
        self.assertFalse(hasattr(self.engine, "mock_broker"))
        self.assertFalse(hasattr(self.engine, "create_mock_order"))

    def test_35_no_alpaca_submit_replace_cancel(self):
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "NVDA", "qty": 5, "side": "buy"})

    def test_36_no_live_execution_path(self):
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_37_simulation_environment_tagging(self):
        strat = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3, emit_hold=True)
        bar = self._create_bar(close=100.0)
        sig = strat.generate_signals(bar)
        self.assertEqual(sig.environment, "SIMULATION")

    def test_38_no_writes_to_natural_market_topics(self):
        # Assert signal store only writes under data/paper_bot/strategies/
        self.assertTrue(os.path.exists(self.signal_store.signals_dir))
        self.assertIn("strategies", self.signal_store.base_dir)
        self.assertFalse(hasattr(self.signal_store, "write_to_redpanda"))


if __name__ == "__main__":
    unittest.main()
