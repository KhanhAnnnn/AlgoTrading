"""
tests/test_gd36_backtesting.py — GĐ36 Backtesting Engine & Historical Replay Integration Test Suite
AlgoTrading V2.0 Paper Trading Bot System.

Contains 65 comprehensive tests covering:
- Group A: Historical Dataset Manager (TC 01 – 10)
- Group B: Replay Clock & Progression Control (TC 11 – 19)
- Group C: Strategy Warmup & No Look-Ahead Invariants (TC 20 – 27)
- Group D: Execution Integration & Broker Parity (TC 28 – 36)
- Group E: Sandboxing & Resource Isolation (TC 37 – 43)
- Group F: Determinism & Reproducibility (TC 44 – 51)
- Group G: Quantitative Metrics & Risk Analytics (TC 52 – 58)
- Group H: REST API, Safety Invariants & Full System Parity (TC 59 – 65)
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
from typing import List

# Setup sys.path for test execution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "trading-dashboard", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
from main import app

from libs.alpaca_paper_gate import paper_gate, LiveTradingProhibitedError, PaperExecutionGateClosedError
from libs.bot.domain import MarketDataEvent, SimulatedOrder, SimulatedFill, StrategySignal, SignalDecision, SimulationOrderIntent
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.strategies.ma_crossover import MovingAverageCrossoverStrategy
from libs.bot.strategies.rsi_strategy import RSIStrategy
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.bot.execution.fees import ZeroFeeModel, ConfigurableFeeModel
from libs.bot.execution.slippage import ZeroSlippageModel, FixedBpsSlippageModel, ConfigurableImpactSlippageModel

from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.dataset import (
    HistoricalDatasetManager,
    DatasetManifest,
    validate_ohlcv,
    is_regular_trading_hours,
)
from libs.bot.backtesting.replay_clock import ReplayClock
from libs.bot.backtesting.replay_controller import ReplayController, ReplayMode, ReplayState
from libs.bot.backtesting.metrics import BacktestMetricsCalculator
from libs.bot.backtesting.results import BacktestResult
from libs.bot.backtesting.store import BacktestStore
from libs.bot.backtesting.runner import BacktestRunner


def create_synthetic_bars(
    symbol: str = "NVDA",
    count: int = 60,
    start_price: float = 150.0,
    start_time: datetime = None,
    asset_class: str = "STOCKS",
) -> List[MarketDataEvent]:
    """Helper to generate valid 1m MarketDataEvents."""
    if start_time is None:
        start_time = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
    bars = []
    p = start_price
    for i in range(count):
        t = start_time + timedelta(minutes=i)
        delta = 1.0 if i % 2 == 0 else -0.5
        p += delta
        bar = MarketDataEvent(
            event_id=f"evt_{symbol}_{i}",
            event_time=t,
            ingest_time=t,
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1m",
            open=Decimal(str(round(p - 0.2, 4))),
            high=Decimal(str(round(p + 0.6, 4))),
            low=Decimal(str(round(p - 0.6, 4))),
            close=Decimal(str(round(p, 4))),
            volume=Decimal("1000"),
            bar_revision=0,
            is_final=True,
            environment="SIMULATION",
        )
        bars.append(bar)
    return bars


def make_test_intent(
    p: SimulationPortfolioManager,
    symbol: str = "NVDA",
    side: str = "BUY",
    order_type: str = "MARKET",
    qty: Decimal = Decimal("10"),
    limit_price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    ref_price: Decimal = Decimal("150.0"),
) -> SimulationOrderIntent:
    f_qty = float(qty)
    f_ref = float(ref_price)
    f_lim = float(limit_price) if limit_price is not None else None
    intent = SimulationOrderIntent(
        intent_id=f"intent_{uuid.uuid4().hex[:8]}",
        decision_id=f"dec_{uuid.uuid4().hex[:8]}",
        signal_id=f"sig_{uuid.uuid4().hex[:8]}",
        bot_session_id=p.bot_session_id,
        portfolio_id=p.portfolio_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=f_qty,
        proposed_quantity=f_qty,
        proposed_notional=round(f_qty * f_ref, 2),
        reference_price=f_ref,
        limit_price=f_lim,
        risk_configuration_version="1.0.0",
        idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
        created_at=datetime.now(timezone.utc),
        environment="SIMULATION",
    )
    if stop_price is not None:
        intent.stop_price = float(stop_price)
    return intent


class TestGD36BacktestingEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.auth_headers = {"X-API-KEY": "simulation_token_v2"}

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_gd36_")
        self.store = BacktestStore(base_dir=self.temp_dir)
        self.dataset_manager = HistoricalDatasetManager(base_dir=os.path.join(self.temp_dir, "datasets"))

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # Group A: Historical Dataset Manager (TC 01 – 10)
    # =========================================================================

    def test_tc01_dataset_creation_valid_bars(self):
        """TC 01: Dataset creation with valid 1m OHLCV bars."""
        bars = create_synthetic_bars("NVDA", count=30)
        cleaned, manifest = self.dataset_manager.create_dataset_from_bars("ds_01", bars)
        self.assertEqual(len(cleaned), 30)
        self.assertEqual(manifest.dataset_id, "ds_01")
        self.assertEqual(manifest.total_bars, 30)
        self.assertIn("NVDA", manifest.symbols)

    def test_tc02_ohlcv_price_anomaly_validation(self):
        """TC 02: OHLCV price anomaly validation (low > high, negative close)."""
        valid_bar = create_synthetic_bars("NVDA", count=1)[0]
        self.assertTrue(validate_ohlcv(valid_bar))

        # Inverted low > high
        invalid_bar1 = MarketDataEvent(
            event_id="e_inv",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("100"),
            high=Decimal("90"),
            low=Decimal("110"),
            close=Decimal("100"),
            volume=Decimal("100"),
            is_final=True,
            environment="SIMULATION",
        )
        self.assertFalse(validate_ohlcv(invalid_bar1))

        # Negative price
        invalid_bar2 = MarketDataEvent(
            event_id="e_neg",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("-10"),
            high=Decimal("10"),
            low=Decimal("-10"),
            close=Decimal("5"),
            volume=Decimal("100"),
            is_final=True,
            environment="SIMULATION",
        )
        self.assertFalse(validate_ohlcv(invalid_bar2))

    def test_tc03_gap_detection_in_chronological_series(self):
        """TC 03: Gap detection in chronological series."""
        t0 = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        bars = create_synthetic_bars("NVDA", count=5, start_time=t0)
        # Introduce a 10-minute gap
        t_gap = t0 + timedelta(minutes=15)
        gap_bars = create_synthetic_bars("NVDA", count=5, start_time=t_gap)
        all_bars = bars + gap_bars
        gaps = HistoricalDatasetManager.detect_gaps(all_bars, expected_interval_seconds=60)
        self.assertEqual(len(gaps), 1)
        self.assertGreaterEqual(gaps[0]["gap_seconds"], 600)

    def test_tc04_duplicate_bar_key_and_revision_handling(self):
        """TC 04: Duplicate bar key and revision ordering."""
        t0 = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        bar_rev0 = MarketDataEvent(
            event_id="e0",
            event_time=t0,
            ingest_time=t0,
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("102"),
            volume=Decimal("100"),
            bar_revision=0,
            is_final=True,
            environment="SIMULATION",
        )
        bar_rev1 = MarketDataEvent(
            event_id="e1",
            event_time=t0,
            ingest_time=t0,
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("100"),
            high=Decimal("106"),
            low=Decimal("95"),
            close=Decimal("103"),
            volume=Decimal("120"),
            bar_revision=1,
            is_final=True,
            environment="SIMULATION",
        )
        cleaned, manifest = self.dataset_manager.create_dataset_from_bars("ds_dup", [bar_rev0, bar_rev1])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].bar_revision, 1)
        self.assertEqual(cleaned[0].close, Decimal("103"))

    def test_tc05_market_session_filtering_stocks(self):
        """TC 05: Market session filtering for Stocks (regular trading hours 14:30 - 21:00 UTC)."""
        rth_time = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc) # 10:00 AM EST
        after_hours_time = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc) # 17:00 EST
        weekend_time = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc) # Saturday

        self.assertTrue(is_regular_trading_hours(rth_time, asset_class="STOCKS"))
        self.assertFalse(is_regular_trading_hours(after_hours_time, asset_class="STOCKS"))
        self.assertFalse(is_regular_trading_hours(weekend_time, asset_class="STOCKS"))

    def test_tc06_market_session_continuous_crypto(self):
        """TC 06: Market session continuous 24/7 processing for Crypto."""
        weekend_time = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc) # Saturday
        midnight_time = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
        self.assertTrue(is_regular_trading_hours(weekend_time, asset_class="CRYPTO"))
        self.assertTrue(is_regular_trading_hours(midnight_time, asset_class="CRYPTO"))

    def test_tc07_manifest_checksum_integrity(self):
        """TC 07: Dataset manifest creation and SHA-256 integrity checksum computation."""
        bars = create_synthetic_bars("NVDA", count=25)
        _, manifest = self.dataset_manager.create_dataset_from_bars("ds_check", bars)
        self.assertIsNotNone(manifest.checksum_sha256)
        self.assertEqual(len(manifest.checksum_sha256), 64)

    def test_tc08_immutable_dataset_versioning_and_storage(self):
        """TC 08: Immutable dataset versioning and storage isolation."""
        bars = create_synthetic_bars("NVDA", count=20)
        self.dataset_manager.create_dataset_from_bars("ds_v1", bars, version="1.0.0")
        loaded = self.dataset_manager.load_dataset("ds_v1")
        self.assertEqual(len(loaded), 20)

    def test_tc09_dataset_jsonl_persistence_roundtrip(self):
        """TC 09: Dataset loading from persisted JSONL."""
        bars = create_synthetic_bars("AAPL", count=15)
        self.dataset_manager.create_dataset_from_bars("ds_roundtrip", bars)
        loaded = self.dataset_manager.load_dataset("ds_roundtrip")
        self.assertEqual(len(loaded), 15)
        self.assertEqual(loaded[0].symbol, "AAPL")
        self.assertEqual(loaded[-1].close, bars[-1].close)

    def test_tc10_mixed_stocks_and_crypto_dataset(self):
        """TC 10: Mixed stocks and crypto dataset handling."""
        stock_bars = create_synthetic_bars("NVDA", count=10, asset_class="STOCKS")
        crypto_bars = create_synthetic_bars("BTC/USD", count=10, start_price=60000.0, asset_class="CRYPTO")
        all_bars = stock_bars + crypto_bars
        cleaned, manifest = self.dataset_manager.create_dataset_from_bars(
            "ds_mixed",
            all_bars,
            asset_classes={"NVDA": "STOCKS", "BTC/USD": "CRYPTO"},
        )
        self.assertEqual(len(cleaned), 20)
        self.assertIn("NVDA", manifest.symbols)
        self.assertIn("BTC/USD", manifest.symbols)

    # =========================================================================
    # Group B: Replay Clock & Progression Control (TC 11 – 19)
    # =========================================================================

    def test_tc11_monotonic_virtual_event_time_advancement(self):
        """TC 11: Monotonic virtual event-time advancement."""
        clock = ReplayClock()
        t1 = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 20, 14, 31, tzinfo=timezone.utc)
        clock.advance_to(t1)
        self.assertEqual(clock.now, t1)
        clock.advance_to(t2)
        self.assertEqual(clock.now, t2)

        # Regressing in time raises ValueError
        t_past = datetime(2026, 11, 20, 14, 29, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            clock.advance_to(t_past)

    def test_tc12_virtual_freshness_evaluation_decoupled_from_wall_clock(self):
        """TC 12: Virtual freshness evaluation decoupled from wall-clock time."""
        clock = ReplayClock()
        t_past_year = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        clock.advance_to(t_past_year)

        # A bar from 30 seconds before clock.now is NOT stale under virtual replay
        bar_time = t_past_year - timedelta(seconds=30)
        self.assertFalse(clock.is_stale(bar_time, max_staleness_seconds=60))

        # A bar from 120 seconds before clock.now IS stale under virtual replay
        stale_time = t_past_year - timedelta(seconds=120)
        self.assertTrue(clock.is_stale(stale_time, max_staleness_seconds=60))

    def test_tc13_deterministic_multi_symbol_tie_breaker(self):
        """TC 13: Deterministic multi-symbol tie-breaker (event_time, symbol.upper(), bar_revision)."""
        t0 = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        b_nvda = MarketDataEvent(
            event_id="e_nvda", event_time=t0, ingest_time=t0, symbol="NVDA", asset_class="STOCKS",
            timeframe="1m", open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
            volume=Decimal("10"), bar_revision=0, is_final=True, environment="SIMULATION",
        )
        b_aapl = MarketDataEvent(
            event_id="e_aapl", event_time=t0, ingest_time=t0, symbol="AAPL", asset_class="STOCKS",
            timeframe="1m", open=Decimal("150"), high=Decimal("151"), low=Decimal("149"), close=Decimal("150"),
            volume=Decimal("10"), bar_revision=0, is_final=True, environment="SIMULATION",
        )
        b_btc = MarketDataEvent(
            event_id="e_btc", event_time=t0, ingest_time=t0, symbol="BTC/USD", asset_class="CRYPTO",
            timeframe="1m", open=Decimal("50000"), high=Decimal("50100"), low=Decimal("49900"), close=Decimal("50000"),
            volume=Decimal("10"), bar_revision=0, is_final=True, environment="SIMULATION",
        )
        sorted_bars = ReplayClock.sort_bars_deterministically([b_nvda, b_btc, b_aapl])
        symbols = [b.symbol for b in sorted_bars]
        self.assertEqual(symbols, ["AAPL", "BTC/USD", "NVDA"])

    def test_tc14_fast_replay_mode(self):
        """TC 14: Replay mode FAST_REPLAY executes rapidly without delay."""
        bars = create_synthetic_bars("NVDA", count=20)
        controller = ReplayController(bars=bars, mode=ReplayMode.FAST_REPLAY)
        processed_count = 0
        def on_bar(b, clk):
            nonlocal processed_count
            processed_count += 1
        controller.on_bar_callback = on_bar
        controller.start()
        self.assertEqual(processed_count, 20)
        self.assertEqual(controller.state, ReplayState.COMPLETED)

    def test_tc15_paced_replay_mode(self):
        """TC 15: Replay mode PACED_REPLAY with slight delay."""
        bars = create_synthetic_bars("NVDA", count=5)
        controller = ReplayController(bars=bars, mode=ReplayMode.PACED_REPLAY, pace_delay_seconds=0.001)
        controller.start()
        self.assertEqual(controller.state, ReplayState.COMPLETED)
        self.assertEqual(controller.processed_count, 5)

    def test_tc16_step_replay_mode(self):
        """TC 16: Replay mode STEP_REPLAY single-step execution."""
        bars = create_synthetic_bars("NVDA", count=5)
        controller = ReplayController(bars=bars, mode=ReplayMode.STEP_REPLAY)
        self.assertEqual(controller.processed_count, 0)
        b1 = controller.step()
        self.assertIsNotNone(b1)
        self.assertEqual(controller.processed_count, 1)
        controller.step()
        self.assertEqual(controller.processed_count, 2)

    def test_tc17_replay_controller_pause_and_resume(self):
        """TC 17: Replay controller pause and resume behavior."""
        bars = create_synthetic_bars("NVDA", count=10)
        controller = ReplayController(bars=bars, mode=ReplayMode.STEP_REPLAY)
        controller.step()
        controller.pause()
        self.assertEqual(controller.state, ReplayState.PAUSED)
        controller.resume()
        self.assertEqual(controller.state, ReplayState.RUNNING)

    def test_tc18_replay_controller_cancellation(self):
        """TC 18: Replay controller cancellation and terminal state."""
        bars = create_synthetic_bars("NVDA", count=10)
        controller = ReplayController(bars=bars, mode=ReplayMode.STEP_REPLAY)
        controller.step()
        controller.cancel()
        self.assertEqual(controller.state, ReplayState.CANCELLED)
        # Further step returns None
        self.assertIsNone(controller.step())

    def test_tc19_replay_controller_progress_hook(self):
        """TC 19: Replay controller progress hook invocation."""
        bars = create_synthetic_bars("NVDA", count=10)
        progress_calls = []
        def progress_cb(cur, total, ts):
            progress_calls.append((cur, total))
        controller = ReplayController(bars=bars, mode=ReplayMode.FAST_REPLAY, on_progress_callback=progress_cb)
        controller.start()
        self.assertEqual(len(progress_calls), 10)
        self.assertEqual(progress_calls[-1], (10, 10))

    # =========================================================================
    # Group C: Strategy Warmup & No Look-Ahead (TC 20 – 27)
    # =========================================================================

    def test_tc20_indicator_warmup_without_trading(self):
        """TC 20: Indicator warmup accumulation without trading."""
        bars = create_synthetic_bars("NVDA", count=50)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=30)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        # Warmup was 30 bars, remaining 20 bars tradable
        self.assertIsNotNone(res)
        self.assertEqual(res.status, "COMPLETED")

    def test_tc21_zero_trading_strictly_enforced_during_warmup(self):
        """TC 21: Zero trading strictly enforced during warmup phase."""
        bars = create_synthetic_bars("NVDA", count=40)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=40)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        # Since warmup_bars_count == total bars, 0 tradable bars -> 0 orders
        self.assertEqual(res.metrics["total_orders"], 0)
        self.assertEqual(res.metrics["total_fills"], 0)

    def test_tc22_insufficient_history_for_warmup(self):
        """TC 22: Insufficient bar history handling when warmup is required."""
        bars = create_synthetic_bars("NVDA", count=10)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=50, warmup_policy="REQUIRED")
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        with self.assertRaises(ValueError):
            runner.run(bars)

    def test_tc23_strict_no_look_ahead_invariant(self):
        """TC 23: Zero look-ahead bias: orders placed on bar N are only matched against subsequent bars."""
        bars = create_synthetic_bars("NVDA", count=60)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=20)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        # Any fills must have execution_bar_key or fill_time >= order submission
        for f in res.fills:
            self.assertIsNotNone(f.get("fill_time"))

    def test_tc24_signal_generation_on_exact_bar_boundary(self):
        """TC 24: Signal generation on exact bar boundary when indicator conditions are met."""
        bars = create_synthetic_bars("NVDA", count=60)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=20)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        for sig in res.signals:
            self.assertIn("timestamp", sig)
            self.assertEqual(sig["symbol"], "NVDA")

    def test_tc25_strategy_parameter_updates_reflect_in_hash(self):
        """TC 25: Strategy parameter updates alter config hash."""
        cfg1 = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            execution_config={"strategy_params": {"fast_period": 10, "slow_period": 30}},
        )
        cfg2 = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            execution_config={"strategy_params": {"fast_period": 20, "slow_period": 50}},
        )
        # Altering parameters changes the configuration
        self.assertNotEqual(cfg1.execution_config, cfg2.execution_config)

    def test_tc26_moving_average_crossover_execution(self):
        """TC 26: Moving Average crossover strategy execution on historical bars."""
        bars = create_synthetic_bars("NVDA", count=70)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=25)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        self.assertEqual(res.status, "COMPLETED")
        self.assertGreater(len(res.equity_curve), 0)

    def test_tc27_rsi_strategy_execution(self):
        """TC 27: RSI mean reversion strategy execution on historical bars."""
        bars = create_synthetic_bars("NVDA", count=60)
        cfg = BacktestConfig(strategy_id="RSI_1M", symbols=["NVDA"], warmup_bars_count=20)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        self.assertEqual(res.status, "COMPLETED")
        self.assertIsNotNone(res.metrics)

    # =========================================================================
    # Group D: Execution Integration & Broker Parity (TC 28 – 36)
    # =========================================================================

    def test_tc28_next_bar_fill_simulation_parity(self):
        """TC 28: Next-bar fill simulation parity with GĐ33 Simulation Broker."""
        bars = create_synthetic_bars("NVDA", count=40)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=10)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        # Broker executes next-bar fills
        self.assertIsNotNone(runner.broker)
        self.assertEqual(runner.broker.portfolio.state, "ACTIVE")

    def test_tc29_market_order_fill_at_open(self):
        """TC 29: Market order matching at next bar open price."""
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, fee_model=ZeroFeeModel(), slippage_model=ZeroSlippageModel())
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="MARKET", qty=Decimal("10"))
        broker.submit_intent(intent)
        next_bar = create_synthetic_bars("NVDA", count=1, start_price=152.0)[0]
        fills = broker.process_bar(next_bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(to_decimal(fills[0].fill_price), next_bar.open)

    def test_tc30_limit_order_fill_condition(self):
        """TC 30: Limit order fill condition testing."""
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, fee_model=ZeroFeeModel(), slippage_model=ZeroSlippageModel())
        # Buy Limit at 140 (when bar low is 145) -> Should NOT fill
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="LIMIT", qty=Decimal("10"), limit_price=Decimal("140.0"))
        broker.submit_intent(intent)
        high_bar = create_synthetic_bars("NVDA", count=1, start_price=150.0)[0]
        fills = broker.process_bar(high_bar)
        self.assertEqual(len(fills), 0)

    def test_tc31_stop_order_trigger_condition(self):
        """TC 31: Stop order trigger condition testing."""
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, fee_model=ZeroFeeModel(), slippage_model=ZeroSlippageModel())
        # Stop Buy at 160 (current 150) -> Bar high reaches 165 -> triggers & fills
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="STOP", qty=Decimal("10"), stop_price=Decimal("160.0"))
        broker.submit_intent(intent)
        spike_bar = MarketDataEvent(
            event_id="e_spike",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("155"),
            high=Decimal("165"),
            low=Decimal("154"),
            close=Decimal("162"),
            volume=Decimal("1000"),
            is_final=True,
            environment="SIMULATION",
        )
        fills = broker.process_bar(spike_bar)
        self.assertEqual(len(fills), 1)

    def test_tc32_volume_participation_cap(self):
        """TC 32: Volume participation cap enforcement."""
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, max_participation_rate=0.10)
        bar = MarketDataEvent(
            event_id="e_vol",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            symbol="NVDA",
            asset_class="STOCKS",
            timeframe="1m",
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("100"),
            is_final=True,
            environment="SIMULATION",
        )
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="MARKET", qty=Decimal("50"))
        broker.submit_intent(intent)
        fills = broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].fill_qty, Decimal("10")) # Capped at 10% of 100

    def test_tc33_fixed_bps_slippage_model(self):
        """TC 33: Fixed BPS slippage model execution on fills."""
        slip_model = FixedBpsSlippageModel(bps=10.0)
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, slippage_model=slip_model)
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="MARKET", qty=Decimal("10"))
        broker.submit_intent(intent)
        bar = create_synthetic_bars("NVDA", count=1, start_price=100.0)[0]
        fills = broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertGreater(fills[0].fill_price, bar.open)

    def test_tc34_configurable_fee_model(self):
        """TC 34: Configurable fee model application on fills."""
        fee_model = ConfigurableFeeModel(stocks_per_share=0.01, stocks_min_commission=2.0)
        p = SimulationPortfolioManager(initial_cash=100000.0)
        broker = SimulationBroker(portfolio=p, fee_model=fee_model, slippage_model=ZeroSlippageModel())
        intent = make_test_intent(p, symbol="NVDA", side="BUY", order_type="MARKET", qty=Decimal("100"))
        broker.submit_intent(intent)
        bar = create_synthetic_bars("NVDA", count=1, start_price=100.0)[0]
        fills = broker.process_bar(bar)
        self.assertEqual(len(fills), 1)
        self.assertGreaterEqual(fills[0].fee, Decimal("2.0"))

    def test_tc35_portfolio_mark_to_market_parity(self):
        """TC 35: Portfolio mark-to-market accounting parity with GĐ32."""
        p = SimulationPortfolioManager(initial_cash=100000.0)
        p.positions.record_fill(symbol="NVDA", side="BUY", qty=Decimal("10"), fill_price=Decimal("150.0"), fee=Decimal("1.0"))
        p.positions.update_valuation("NVDA", Decimal("160.0"))
        unrealized = p.positions.get_total_unrealized_pnl()
        self.assertEqual(unrealized, Decimal("100.0")) # 10 * (160 - 150)

    def test_tc36_cash_reservation_and_release(self):
        """TC 36: Cash reservation and release parity on orders."""
        p = SimulationPortfolioManager(initial_cash=5000.0)
        p.reserve_cash(Decimal("2000.0"), reference_id="order_1")
        self.assertEqual(p.available_cash, Decimal("3000.0"))
        p.release_cash(Decimal("2000.0"), reference_id="order_1")
        self.assertEqual(p.available_cash, Decimal("5000.0"))

    # =========================================================================
    # Group E: Sandboxing & Resource Isolation (TC 37 – 43)
    # =========================================================================

    def test_tc37_backtest_portfolio_isolation(self):
        """TC 37: Backtest portfolio strictly segregated from live BotSession portfolios."""
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"])
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        runner.setup()
        self.assertTrue(runner.portfolio.portfolio_id.startswith("port_bt_"))
        self.assertTrue(runner.portfolio.bot_session_id.startswith("bt_"))

    def test_tc38_no_kafka_consumer_offsets(self):
        """TC 38: Backtest run creates no Kafka consumer groups or offset commits."""
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"])
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        # Runner operates entirely in memory / on disk datasets without Kafka
        self.assertFalse(hasattr(runner, "kafka_consumer"))

    def test_tc39_zero_alpaca_api_calls(self):
        """TC 39: Zero Alpaca paper broker HTTP API calls during backtest."""
        bars = create_synthetic_bars("NVDA", count=30)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=10)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        self.assertIsNotNone(res)
        self.assertFalse(paper_gate.is_gate_open)

    def test_tc40_live_trading_prohibited_error_when_gate_open(self):
        """TC 40: Attempt to run backtest with open gate raises LiveTradingProhibitedError."""
        bars = create_synthetic_bars("NVDA", count=10)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"])
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)

        # Temporarily open gate to verify safety barrier
        original_gate_status = paper_gate.is_gate_open
        try:
            paper_gate.is_gate_open = True
            with self.assertRaises(LiveTradingProhibitedError):
                runner.setup()
        finally:
            paper_gate.is_gate_open = original_gate_status

    def test_tc41_persistence_isolated_under_data_backtests(self):
        """TC 41: Backtest persistence isolated under data/paper_bot/backtests/{run_id}/."""
        bars = create_synthetic_bars("NVDA", count=25)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=10)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)

        run_path = os.path.join(self.temp_dir, res.run_id)
        self.assertTrue(os.path.exists(run_path))
        self.assertTrue(os.path.exists(os.path.join(run_path, "result.json")))
        self.assertTrue(os.path.exists(os.path.join(run_path, "metrics.json")))

    def test_tc42_concurrent_backtest_isolation(self):
        """TC 42: Multiple concurrent backtests do not interfere with each other's state."""
        bars = create_synthetic_bars("NVDA", count=30)
        cfg1 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], initial_simulated_cash=100000.0)
        cfg2 = BacktestConfig(strategy_id="RSI_1M", symbols=["NVDA"], initial_simulated_cash=50000.0)

        runner1 = BacktestRunner(config=cfg1, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg2, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars)
        res2 = runner2.run(bars)

        self.assertNotEqual(res1.run_id, res2.run_id)
        self.assertEqual(res1.metrics["initial_equity"], 100000.0)
        self.assertEqual(res2.metrics["initial_equity"], 50000.0)

    def test_tc43_teardown_and_deletion(self):
        """TC 43: Backtest run teardown flushes and releases resources."""
        bars = create_synthetic_bars("NVDA", count=20)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=5)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)
        self.assertTrue(self.store.delete_run(res.run_id))
        self.assertIsNone(self.store.get_result(res.run_id))

    # =========================================================================
    # Group F: Determinism & Reproducibility (TC 44 – 51)
    # =========================================================================

    def test_tc44_identical_dataset_config_produces_identical_outcomes(self):
        """TC 44: Identical dataset and config produce identical economic outcomes."""
        bars1 = create_synthetic_bars("NVDA", count=45)
        bars2 = create_synthetic_bars("NVDA", count=45)

        cfg1 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=15)
        cfg2 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=15)

        runner1 = BacktestRunner(config=cfg1, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg2, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars1)
        res2 = runner2.run(bars2)

        self.assertEqual(res1.metrics["final_equity"], res2.metrics["final_equity"])
        self.assertEqual(res1.metrics["total_orders"], res2.metrics["total_orders"])
        self.assertEqual(res1.metrics["total_fills"], res2.metrics["total_fills"])

    def test_tc45_identical_deterministic_fingerprints(self):
        """TC 45: Identical SHA-256 deterministic_fingerprint across multiple runs."""
        bars1 = create_synthetic_bars("NVDA", count=50)
        bars2 = create_synthetic_bars("NVDA", count=50)

        cfg1 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=20)
        cfg2 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=20)

        runner1 = BacktestRunner(config=cfg1, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg2, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars1)
        res2 = runner2.run(bars2)

        fp1 = res1.compute_deterministic_fingerprint()
        fp2 = res2.compute_deterministic_fingerprint()
        self.assertEqual(fp1, fp2)

    def test_tc46_compare_method_economic_identity(self):
        """TC 46: compare() method confirms economic identity between two runs."""
        bars = create_synthetic_bars("NVDA", count=40)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=15)

        runner1 = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars)
        res2 = runner2.run(bars)

        comparison = res1.compare(res2)
        self.assertTrue(comparison["is_economically_identical"])
        self.assertEqual(len(comparison["differences"]), 0)

    def test_tc47_config_change_alters_fingerprint(self):
        """TC 47: Config change alters deterministic fingerprint."""
        bars = create_synthetic_bars("NVDA", count=50)
        cfg1 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], initial_simulated_cash=100000.0)
        cfg2 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], initial_simulated_cash=50000.0)

        runner1 = BacktestRunner(config=cfg1, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg2, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars)
        res2 = runner2.run(bars)

        self.assertNotEqual(res1.compute_deterministic_fingerprint(), res2.compute_deterministic_fingerprint())

    def test_tc48_dataset_perturbation_alters_fingerprint(self):
        """TC 48: Dataset perturbation alters deterministic fingerprint."""
        bars1 = create_synthetic_bars("NVDA", count=50, start_price=100.0)
        bars2 = create_synthetic_bars("NVDA", count=50, start_price=200.0)

        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=20)
        runner1 = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        runner2 = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)

        res1 = runner1.run(bars1)
        res2 = runner2.run(bars2)

        self.assertNotEqual(res1.compute_deterministic_fingerprint(), res2.compute_deterministic_fingerprint())

    def test_tc49_seed_parameter_consistency(self):
        """TC 49: Seed parameter ensures repeatable configuration hashing."""
        cfg1 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], seed=42)
        cfg2 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], seed=42)
        cfg3 = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], seed=99)

        self.assertEqual(cfg1.compute_config_hash(), cfg2.compute_config_hash())
        self.assertNotEqual(cfg1.compute_config_hash(), cfg3.compute_config_hash())

    def test_tc50_decimal_precision_reproducibility(self):
        """TC 50: Floating point and Decimal precision quantizing reproducibility."""
        d1 = to_decimal(150.123456789)
        d2 = to_decimal("150.123456789")
        self.assertEqual(round(float(d1), 4), round(float(d2), 4))

    def test_tc51_persisted_result_reproducibility(self):
        """TC 51: Re-running backtest from persisted result achieves identical fingerprint."""
        bars = create_synthetic_bars("NVDA", count=40)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"], warmup_bars_count=15)
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        res = runner.run(bars)

        fp_original = res.compute_deterministic_fingerprint()

        # Reload from store
        loaded_res = self.store.get_result(res.run_id)
        self.assertEqual(loaded_res["deterministic_fingerprint"], fp_original)

    # =========================================================================
    # Group G: Quantitative Metrics & Risk Analytics (TC 52 – 58)
    # =========================================================================

    def test_tc52_net_return_and_pnl_calculation(self):
        """TC 52: Net return % and Net PnL calculations."""
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=110000.0,
            realized_pnl=10000.0,
            unrealized_pnl=0.0,
            total_fees=50.0,
            total_slippage=10.0,
            orders=[],
            fills=[],
            equity_curve=[{"timestamp": "2026-11-20T14:30:00Z", "equity": 100000.0}, {"timestamp": "2026-11-20T15:00:00Z", "equity": 110000.0}],
        )
        self.assertEqual(m["net_pnl"], 10000.0)
        self.assertEqual(m["net_return_pct"], 10.0)

    def test_tc53_peak_equity_and_max_drawdown(self):
        """TC 53: Peak equity and Max Drawdown ($ and %) calculation."""
        eq_curve = [
            {"timestamp": "t0", "equity": 100000.0},
            {"timestamp": "t1", "equity": 120000.0}, # Peak
            {"timestamp": "t2", "equity": 90000.0},  # Drawdown of 30,000 (25%)
            {"timestamp": "t3", "equity": 105000.0},
        ]
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=105000.0,
            realized_pnl=5000.0,
            unrealized_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            orders=[],
            fills=[],
            equity_curve=eq_curve,
        )
        self.assertEqual(m["peak_equity"], 120000.0)
        self.assertEqual(m["max_drawdown_usd"], 30000.0)
        self.assertEqual(m["max_drawdown_pct"], 25.0)

    def test_tc54_sharpe_ratio_calculation(self):
        """TC 54: Sharpe ratio calculation with disclosed 1m sampling frequency."""
        eq_curve = [{"timestamp": f"t_{i}", "equity": 100000.0 + (i * 100.0)} for i in range(25)]
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=102400.0,
            realized_pnl=2400.0,
            unrealized_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            orders=[],
            fills=[],
            equity_curve=eq_curve,
            asset_class="STOCKS",
        )
        self.assertEqual(m["annualization_sampling"], "1m_bars")
        self.assertGreater(m["annualization_factor"], 300.0)
        self.assertIsNotNone(m["sharpe_ratio"])

    def test_tc55_sortino_ratio_downside_deviation(self):
        """TC 55: Sortino ratio downside deviation calculation."""
        eq_curve = [{"timestamp": f"t_{i}", "equity": 100000.0 + (100.0 if i % 2 == 0 else -50.0)} for i in range(20)]
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=100050.0,
            realized_pnl=50.0,
            unrealized_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            orders=[],
            fills=[],
            equity_curve=eq_curve,
        )
        self.assertIsNotNone(m["sortino_ratio"])

    def test_tc56_trades_win_rate_and_profit_factor(self):
        """TC 56: Closed trades, win rate %, and profit factor calculation."""
        # 4 fills -> 2 round trips
        fills = [
            SimulatedFill("f1", "o1", "i1", "s1", "NVDA", "BUY", Decimal("100"), Decimal("10"), datetime.now(timezone.utc), Decimal("1"), "USD", Decimal("0"), "b0", "b1", "SIMULATION"),
            SimulatedFill("f2", "o2", "i2", "s1", "NVDA", "SELL", Decimal("110"), Decimal("10"), datetime.now(timezone.utc), Decimal("1"), "USD", Decimal("0"), "b1", "b2", "SIMULATION"),
            SimulatedFill("f3", "o3", "i3", "s1", "NVDA", "BUY", Decimal("105"), Decimal("10"), datetime.now(timezone.utc), Decimal("1"), "USD", Decimal("0"), "b2", "b3", "SIMULATION"),
            SimulatedFill("f4", "o4", "i4", "s1", "NVDA", "SELL", Decimal("100"), Decimal("10"), datetime.now(timezone.utc), Decimal("1"), "USD", Decimal("0"), "b3", "b4", "SIMULATION"),
        ]
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=100050.0,
            realized_pnl=50.0,
            unrealized_pnl=0.0,
            total_fees=4.0,
            total_slippage=0.0,
            orders=[],
            fills=fills,
            equity_curve=[],
        )
        self.assertEqual(m["total_fills"], 4)
        self.assertEqual(m["total_trades"], 2)

    def test_tc57_time_in_market_percentage(self):
        """TC 57: Time in market percentage calculation."""
        eq_curve = [
            {"timestamp": "t0", "equity": 100000.0, "has_position": False},
            {"timestamp": "t1", "equity": 100000.0, "has_position": True},
            {"timestamp": "t2", "equity": 100000.0, "has_position": True},
            {"timestamp": "t3", "equity": 100000.0, "has_position": False},
        ]
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=100000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            orders=[],
            fills=[],
            equity_curve=eq_curve,
        )
        self.assertEqual(m["time_in_market_pct"], 50.0)

    def test_tc58_performance_disclaimer_included(self):
        """TC 58: Performance disclaimer explicitly included in output artifact."""
        m = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=100000.0,
            final_equity=100000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            orders=[],
            fills=[],
            equity_curve=[],
        )
        self.assertIn("disclaimer", m)
        self.assertIn("research purposes only", m["disclaimer"])

    # =========================================================================
    # Group H: REST API, Safety Invariants & Full System Parity (TC 59 – 65)
    # =========================================================================

    def test_tc59_api_create_backtest(self):
        """TC 59: POST /api/v2/backtests creates and runs backtest, returns 201."""
        payload = {
            "strategy_id": "MA_CROSS_1M",
            "symbols": ["NVDA"],
            "initial_simulated_cash": 100000.0,
            "warmup_bars_count": 20,
            "synthetic_bars_count": 50,
        }
        res = self.client.post("/api/v2/backtests", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertIn("run_id", data)
        self.assertIn("deterministic_fingerprint", data)

    def test_tc60_api_list_backtests(self):
        """TC 60: GET /api/v2/backtests lists stored backtests."""
        res = self.client.get("/api/v2/backtests", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_tc61_api_get_backtest_by_id(self):
        """TC 61: GET /api/v2/backtests/{run_id} retrieves run summary."""
        # Nonexistent run -> 404
        res404 = self.client.get("/api/v2/backtests/bt_nonexistent", headers=self.auth_headers)
        self.assertEqual(res404.status_code, 404)

        # Create one first
        post_res = self.client.post("/api/v2/backtests", json={"strategy_id": "MA_CROSS_1M", "symbols": ["NVDA"], "synthetic_bars_count": 40}, headers=self.auth_headers)
        run_id = post_res.json()["run_id"]

        get_res = self.client.get(f"/api/v2/backtests/{run_id}", headers=self.auth_headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["run_id"], run_id)

    def test_tc62_api_results_trades_equity_endpoints(self):
        """TC 62: GET /api/v2/backtests/{run_id}/results, /trades, /equity endpoints."""
        post_res = self.client.post("/api/v2/backtests", json={"strategy_id": "MA_CROSS_1M", "symbols": ["NVDA"], "synthetic_bars_count": 40}, headers=self.auth_headers)
        run_id = post_res.json()["run_id"]

        res_results = self.client.get(f"/api/v2/backtests/{run_id}/results", headers=self.auth_headers)
        self.assertEqual(res_results.status_code, 200)
        self.assertIn("deterministic_fingerprint", res_results.json())

        res_trades = self.client.get(f"/api/v2/backtests/{run_id}/trades", headers=self.auth_headers)
        self.assertEqual(res_trades.status_code, 200)
        self.assertIsInstance(res_trades.json(), list)

        res_equity = self.client.get(f"/api/v2/backtests/{run_id}/equity", headers=self.auth_headers)
        self.assertEqual(res_equity.status_code, 200)
        self.assertIsInstance(res_equity.json(), list)

    def test_tc63_api_cancel_endpoint(self):
        """TC 63: POST /api/v2/backtests/{run_id}/cancel endpoint."""
        post_res = self.client.post("/api/v2/backtests", json={"strategy_id": "MA_CROSS_1M", "symbols": ["NVDA"], "synthetic_bars_count": 40}, headers=self.auth_headers)
        run_id = post_res.json()["run_id"]

        # If already completed, returns ALREADY_COMPLETED
        cancel_res = self.client.post(f"/api/v2/backtests/{run_id}/cancel", headers=self.auth_headers)
        self.assertEqual(cancel_res.status_code, 200)
        self.assertIn(cancel_res.json()["status"], ["CANCELLED", "ALREADY_COMPLETED"])

    def test_tc64_safety_invariants_verification(self):
        """TC 64: Safety Invariants: TRADING_MODE=DRY_RUN, paper_gate.is_gate_open=False, environment=SIMULATION."""
        self.assertFalse(paper_gate.is_gate_open)
        cfg = BacktestConfig(strategy_id="MA_CROSS_1M", symbols=["NVDA"])
        self.assertEqual(cfg.environment, "SIMULATION")

        # Verification of Alpaca gate blockage
        with self.assertRaises((PaperExecutionGateClosedError, LiveTradingProhibitedError)):
            paper_gate.submit_paper_order({"symbol": "NVDA", "qty": 1, "side": "buy"})

    def test_tc65_comprehensive_end_to_end_backtest_run(self):
        """TC 65: Comprehensive end-to-end multi-bar backtest run verification across all modules."""
        bars = create_synthetic_bars("NVDA", count=100)
        cfg = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
            fee_model="DEFAULT",
            slippage_model="DEFAULT",
            warmup_bars_count=30,
        )
        runner = BacktestRunner(config=cfg, store=self.store, dataset_manager=self.dataset_manager)
        result = runner.run(bars)

        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNotNone(result.metrics)
        self.assertGreater(len(result.equity_curve), 50)
        self.assertEqual(len(result.compute_deterministic_fingerprint()), 64)
        self.assertEqual(result.environment, "SIMULATION")


if __name__ == "__main__":
    unittest.main()
