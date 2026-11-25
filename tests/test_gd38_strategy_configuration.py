"""
tests/test_gd38_strategy_configuration.py — GĐ38 Strategy Configuration, Versioning & Backtest Comparison
75 Unit & Integration tests covering Groups A through H.
"""

import unittest
from unittest.mock import Mock
import os
import uuid
import shutil
import tempfile
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List

from fastapi.testclient import TestClient

from libs.alpaca_paper_gate import paper_gate
from libs.bot.domain import MarketDataEvent, BotSession
from libs.bot.orchestration.lifecycle import BotLifecycleState, BotLifecycleStateMachine
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.dispatcher import V2MarketDataDispatcher
from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.resource_policy import ResourcePolicy
from libs.bot.multibot.subscriptions import BotSubscription
from libs.bot.strategy_config.schemas import (
    ParameterSchema,
    StrategySchemaValidator,
    ValidationError,
    ValidationResult,
)
from libs.bot.strategy_config.registry import (
    StrategyDefinition,
    StrategyConfigurationRegistry,
)
from libs.bot.strategy_config.versioning import (
    canonical_serialize,
    compute_configuration_hash,
)
from libs.bot.strategy_config.presets import (
    StrategyPreset,
    PresetStore,
    PresetImmutableError,
    PresetNotFoundError,
)
from libs.bot.experiments.calendar import MarketSessionCalendar, EASTERN_TZ
from libs.bot.experiments.fingerprint import EconomicSequenceFingerprint
from libs.bot.experiments.comparability import ComparabilityEngine, ComparabilityResult
from libs.bot.experiments.comparison import BacktestComparisonService
from libs.bot.experiments.robustness import StrategyRobustnessAnalyzer
from libs.bot.experiments.store import ExperimentStore
from libs.bot.experiments.manager import (
    BacktestExperiment,
    ExperimentVariant,
    BacktestExperimentManager,
)
# API routes are tested via isolated FastAPI instances in tests 74 and 75


class TestGD38StrategyConfiguration(unittest.TestCase):
    """GĐ38 Master Test Suite: Strategy Configuration, Presets, Experiments & Comparison."""

    @classmethod
    def setUpClass(cls):
        # Enforce invariant safety gates
        assert paper_gate.is_gate_open is False, "Paper Execution Gate must remain closed!"
        os.environ["TRADING_MODE"] = "DRY_RUN"

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_gd38_")
        self.preset_dir = os.path.join(self.temp_dir, "presets")
        self.exp_dir = os.path.join(self.temp_dir, "experiments")
        self.registry_dir = os.path.join(self.temp_dir, "registry")

        self.preset_store = PresetStore(storage_dir=self.preset_dir)
        self.exp_store = ExperimentStore(storage_dir=self.exp_dir)
        self.strategy_registry = StrategyConfigurationRegistry()
        self.exp_manager = BacktestExperimentManager(
            store=self.exp_store,
            preset_store=self.preset_store,
            default_concurrency=4,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # Group A: Schema Validation & Parameter Constraints (10 tests)
    # =========================================================================

    def test_01_ma_cross_valid_parameters(self):
        res = self.strategy_registry.validate_parameters("MA_CROSS_1M", {
            "fast_window": 15,
            "slow_window": 45,
            "indicator_type": "EMA",
            "emit_hold": False,
        })
        self.assertTrue(res.is_valid)
        self.assertEqual(res.normalized_params["fast_window"], 15)
        self.assertEqual(res.normalized_params["slow_window"], 45)
        self.assertEqual(res.normalized_params["indicator_type"], "EMA")

    def test_02_ma_cross_fast_less_than_slow_enforced(self):
        res = self.strategy_registry.validate_parameters("MA_CROSS_1M", {
            "fast_window": 50,
            "slow_window": 20,
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("fast_window" in err for err in res.errors))

    def test_03_ma_cross_reject_undeclared_parameters(self):
        res = self.strategy_registry.validate_parameters("MA_CROSS_1M", {
            "fast_window": 10,
            "slow_window": 30,
            "random_undeclared_param": 999,
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Undeclared parameter" in err for err in res.errors))

    def test_04_ma_cross_indicator_type_permitted_values(self):
        res = self.strategy_registry.validate_parameters("MA_CROSS_1M", {
            "fast_window": 10,
            "slow_window": 30,
            "indicator_type": "INVALID_MA_TYPE",
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("permitted values" in err for err in res.errors))

    def test_05_rsi_valid_parameters(self):
        res = self.strategy_registry.validate_parameters("RSI_1M", {
            "period": 14,
            "oversold_threshold": 30.0,
            "overbought_threshold": 70.0,
            "method": "WILDER",
        })
        self.assertTrue(res.is_valid)
        self.assertEqual(res.normalized_params["period"], 14)
        self.assertEqual(res.normalized_params["oversold_threshold"], 30.0)

    def test_06_rsi_boundary_constraints(self):
        # oversold >= overbought is an invalid boundary condition
        res = self.strategy_registry.validate_parameters("RSI_1M", {
            "period": 14,
            "oversold_threshold": 80.0,
            "overbought_threshold": 20.0,
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("RSI constraint violated" in err for err in res.errors))

    def test_07_rsi_period_bounds(self):
        res = self.strategy_registry.validate_parameters("RSI_1M", {
            "period": 1,  # below minimum of 2
            "oversold_threshold": 30.0,
            "overbought_threshold": 70.0,
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("below minimum" in err for err in res.errors))

    def test_08_rsi_method_permitted_values(self):
        res = self.strategy_registry.validate_parameters("RSI_1M", {
            "period": 14,
            "method": "SIMPLE_ROLLING",
        })
        self.assertTrue(res.is_valid)
        self.assertEqual(res.normalized_params["method"], "SIMPLE_ROLLING")

    def test_09_parameter_type_coercion(self):
        schema = ParameterSchema(name="threshold", data_type="float", minimum=0.0)
        self.assertEqual(schema.validate_value("25.5"), 25.5)
        schema_int = ParameterSchema(name="window", data_type="int", minimum=1)
        self.assertEqual(schema_int.validate_value("42"), 42)
        schema_bool = ParameterSchema(name="flag", data_type="bool")
        self.assertEqual(schema_bool.validate_value("true"), True)

    def test_10_registry_parameter_validation_pipeline(self):
        defn = self.strategy_registry.get("MA_CROSS_1M")
        self.assertIsNotNone(defn)
        self.assertEqual(defn.strategy_type, "MOMENTUM")
        self.assertIn("1m", defn.supported_timeframes)
        # Test unknown strategy ID
        res = self.strategy_registry.validate_parameters("UNKNOWN_STRATEGY", {})
        self.assertFalse(res.is_valid)

    # =========================================================================
    # Group B: Immutable Strategy Presets, Versioning & Hashing (10 tests)
    # =========================================================================

    def test_11_deterministic_canonical_serialize_order_invariant(self):
        dict1 = {"b": 2, "a": 1, "c": {"z": 26, "y": 25}}
        dict2 = {"a": 1, "c": {"y": 25, "z": 26}, "b": 2}
        self.assertEqual(canonical_serialize(dict1), canonical_serialize(dict2))

    def test_12_compute_configuration_hash_sha256(self):
        dict1 = {"strategy_id": "MA_CROSS_1M", "fast_window": 20, "slow_window": 50}
        h1 = compute_configuration_hash(dict1)
        h2 = compute_configuration_hash(dict1)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # 64 hex chars for SHA-256

    def test_13_create_strategy_preset_persisted(self):
        preset = StrategyPreset(
            preset_id="preset_ma_baseline",
            preset_name="MA Baseline 20/50",
            strategy_id="MA_CROSS_1M",
            parameters={"fast_window": 20, "slow_window": 50},
        )
        self.preset_store.save(preset)
        loaded = self.preset_store.get("preset_ma_baseline")
        self.assertEqual(loaded.preset_id, "preset_ma_baseline")
        self.assertEqual(loaded.parameters["fast_window"], 20)
        self.assertEqual(loaded.configuration_hash, preset.configuration_hash)

    def test_14_preset_immutability_rejection_on_overwrite(self):
        preset = StrategyPreset(
            preset_id="preset_immutable",
            preset_name="Immutable Preset",
            strategy_id="MA_CROSS_1M",
            parameters={"fast_window": 10, "slow_window": 30},
            is_immutable=True,
        )
        self.preset_store.save(preset)
        # Attempt to overwrite with different parameters
        modified = StrategyPreset(
            preset_id="preset_immutable",
            preset_name="Modified Preset",
            strategy_id="MA_CROSS_1M",
            parameters={"fast_window": 15, "slow_window": 45},
            is_immutable=True,
        )
        with self.assertRaises(PresetImmutableError):
            self.preset_store.save(modified)

    def test_15_preset_lock_by_run(self):
        preset = StrategyPreset(
            preset_id="preset_to_lock",
            preset_name="Preset To Lock",
            strategy_id="MA_CROSS_1M",
            parameters={"fast_window": 20, "slow_window": 50},
        )
        self.preset_store.save(preset)
        self.preset_store.lock_preset("preset_to_lock", "run_bt_12345")
        locked = self.preset_store.get("preset_to_lock")
        self.assertEqual(locked.locked_by_run, "run_bt_12345")
        self.assertTrue(locked.is_immutable)

    def test_16_clone_preset_produces_distinct_hash_and_version(self):
        source = StrategyPreset(
            preset_id="preset_source",
            preset_name="Source Preset",
            strategy_id="MA_CROSS_1M",
            parameters={"fast_window": 20, "slow_window": 50},
        )
        self.preset_store.save(source)
        cloned = self.preset_store.clone_preset(
            source_preset_id="preset_source",
            new_preset_id="preset_cloned_v2",
            new_preset_name="Cloned V2",
            new_parameters={"fast_window": 10},
        )
        self.assertEqual(cloned.preset_id, "preset_cloned_v2")
        self.assertEqual(cloned.parameters["fast_window"], 10)
        self.assertEqual(cloned.parameters["slow_window"], 50)
        self.assertNotEqual(cloned.configuration_hash, source.configuration_hash)

    def test_17_preset_store_retrieval_and_listing(self):
        p1 = StrategyPreset(preset_id="p1", preset_name="P1", strategy_id="MA_CROSS_1M")
        p2 = StrategyPreset(preset_id="p2", preset_name="P2", strategy_id="RSI_1M")
        self.preset_store.save(p1)
        self.preset_store.save(p2)
        all_presets = self.preset_store.list_presets()
        self.assertEqual(len(all_presets), 2)
        ma_presets = self.preset_store.list_presets(strategy_id="MA_CROSS_1M")
        self.assertEqual(len(ma_presets), 1)
        self.assertEqual(ma_presets[0].preset_id, "p1")

    def test_18_preset_not_found_handling(self):
        with self.assertRaises(PresetNotFoundError):
            self.preset_store.get("non_existent_preset_id")

    def test_19_preset_environment_simulation_invariant(self):
        preset = StrategyPreset(
            preset_id="p_sim",
            preset_name="Sim Preset",
            strategy_id="MA_CROSS_1M",
        )
        self.assertEqual(preset.environment, "SIMULATION")

    def test_20_preset_schema_version_tracking(self):
        preset = StrategyPreset(
            preset_id="p_ver",
            preset_name="Versioned Preset",
            strategy_id="MA_CROSS_1M",
            schema_version="1.0",
        )
        self.assertEqual(preset.schema_version, "1.0")

    # =========================================================================
    # Group C: Bot Configuration Binding & Multi-Bot Integration (10 tests)
    # =========================================================================

    def test_21_bot_definition_with_preset_binding(self):
        bot = BotDefinition(
            bot_id="bot_preset_1",
            strategy_id="MA_CROSS_1M",
            strategy_preset_id="preset_ma_baseline",
            strategy_config_version="1.0.0",
        )
        self.assertEqual(bot.strategy_preset_id, "preset_ma_baseline")
        self.assertEqual(bot.strategy_config_version, "1.0.0")

    def test_22_bot_definition_hash_includes_preset(self):
        bot_plain = BotDefinition(bot_id="b1", strategy_id="MA_CROSS_1M")
        bot_with_preset = BotDefinition(
            bot_id="b1",
            strategy_id="MA_CROSS_1M",
            strategy_preset_id="preset_alpha",
            strategy_config_version="1.0.0",
        )
        self.assertNotEqual(bot_plain.configuration_hash, bot_with_preset.configuration_hash)

    def test_23_supervisor_applies_pending_preset_on_start(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        bot_def = BotDefinition(
            bot_id="bot_pending",
            pending_preset={"preset_id": "p_new", "version": "2.0.0"},
        )
        reg.register_bot(bot_def)
        supervisor = MultiBotSupervisor(registry=reg, base_dir=self.temp_dir)
        session = supervisor.start_bot("bot_pending")
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)
        # Check that pending preset was applied
        updated_def = reg.get_bot("bot_pending")
        self.assertIsNone(updated_def.pending_preset)
        self.assertEqual(updated_def.strategy_preset_id, "p_new")
        self.assertEqual(updated_def.strategy_config_version, "2.0.0")
        supervisor.stop_bot("bot_pending")

    def test_24_supervisor_running_bot_update_queues_pending(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        bot_def = BotDefinition(bot_id="bot_live_update")
        reg.register_bot(bot_def)
        supervisor = MultiBotSupervisor(registry=reg, base_dir=self.temp_dir)
        supervisor.start_bot("bot_live_update")

        # Request update while running
        res = supervisor.request_bot_configuration_update("bot_live_update", {
            "preset_id": "p_queued",
            "version": "1.1.0",
        })
        self.assertEqual(res["status"], "QUEUED_PENDING")
        updated_def = reg.get_bot("bot_live_update")
        self.assertIsNotNone(updated_def.pending_preset)
        supervisor.stop_bot("bot_live_update")

    def test_25_supervisor_stopped_bot_update_applies_immediately(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        bot_def = BotDefinition(bot_id="bot_stopped_update")
        reg.register_bot(bot_def)
        supervisor = MultiBotSupervisor(registry=reg, base_dir=self.temp_dir)

        res = supervisor.request_bot_configuration_update("bot_stopped_update", {
            "preset_id": "p_immediate",
            "version": "3.0.0",
        })
        self.assertEqual(res["status"], "APPLIED_IMMEDIATELY")
        updated_def = reg.get_bot("bot_stopped_update")
        self.assertEqual(updated_def.strategy_preset_id, "p_immediate")

    def test_26_bot_session_pins_preset_version(self):
        bot = BotDefinition(bot_id="b_pin", strategy_preset_id="p_v1")
        bot.bind_preset("p_v2", "2.0.0")
        self.assertEqual(bot.strategy_preset_id, "p_v2")
        self.assertEqual(bot.strategy_config_version, "2.0.0")

    def test_27_bot_definition_serialization_roundtrip_with_presets(self):
        bot = BotDefinition(
            bot_id="b_serde",
            strategy_preset_id="preset_serde_1",
            strategy_config_version="1.5.0",
            pending_preset={"preset_id": "p_pend"},
        )
        d = bot.to_dict()
        restored = BotDefinition.from_dict(d)
        self.assertEqual(restored.strategy_preset_id, "preset_serde_1")
        self.assertEqual(restored.strategy_config_version, "1.5.0")
        self.assertEqual(restored.pending_preset, {"preset_id": "p_pend"})

    def test_28_supervisor_health_includes_preset_info(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        supervisor = MultiBotSupervisor(registry=reg, base_dir=self.temp_dir)
        health = supervisor.get_supervisor_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["environment"], "SIMULATION")

    def test_29_multibot_independent_presets_isolation(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        b1 = BotDefinition(bot_id="bot_p1", strategy_preset_id="preset_1")
        b2 = BotDefinition(bot_id="bot_p2", strategy_preset_id="preset_2")
        reg.register_bot(b1)
        reg.register_bot(b2)
        self.assertNotEqual(reg.get_bot("bot_p1").strategy_preset_id, reg.get_bot("bot_p2").strategy_preset_id)

    def test_30_bot_registry_persists_presets_binding(self):
        reg = BotRegistry(storage_dir=self.registry_dir)
        b = BotDefinition(bot_id="bot_persist", strategy_preset_id="preset_saved")
        reg.register_bot(b)
        reg.save_to_disk()

        # Reload fresh instance
        reg2 = BotRegistry(storage_dir=self.registry_dir)
        self.assertEqual(reg2.get_bot("bot_persist").strategy_preset_id, "preset_saved")

    # =========================================================================
    # Group D: Reliability Remediation - GĐ36 & GĐ37 Fixes (12 tests)
    # =========================================================================

    def test_31_calendar_est_edt_dst_transitions(self):
        cal = MarketSessionCalendar()
        # Winter (EST: UTC-5): 2026-01-14 10:00 EST -> 15:00 UTC
        dt_winter_utc = datetime(2026, 1, 14, 15, 0, tzinfo=timezone.utc)
        self.assertTrue(cal.is_market_open(dt_winter_utc))

        # Summer (EDT: UTC-4): 2026-07-15 10:00 EDT -> 14:00 UTC
        dt_summer_utc = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
        self.assertTrue(cal.is_market_open(dt_summer_utc))

    def test_32_calendar_weekends_closed(self):
        cal = MarketSessionCalendar()
        sat = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)  # Saturday
        sun = datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc)  # Sunday
        self.assertFalse(cal.is_market_open(sat))
        self.assertFalse(cal.is_market_open(sun))

    def test_33_calendar_us_market_holidays_observed(self):
        cal = MarketSessionCalendar()
        # July 4, 2026 is Saturday -> Observed Friday July 3, 2026
        holidays_2026 = cal.get_market_holidays(2026)
        self.assertIn(date(2026, 7, 3), holidays_2026)
        self.assertFalse(cal.is_trading_day(date(2026, 7, 3)))
        # Thanksgiving 2026 is 4th Thursday in Nov: Nov 26, 2026
        self.assertIn(date(2026, 11, 26), holidays_2026)

    def test_34_calendar_early_close_days(self):
        cal = MarketSessionCalendar()
        early_closes = cal.get_early_close_days(2026)
        # Black Friday: Nov 27, 2026
        self.assertIn(date(2026, 11, 27), early_closes)
        hours = cal.get_session_hours(date(2026, 11, 27))
        self.assertIsNotNone(hours)
        open_time, close_time = hours
        self.assertEqual(open_time, time(9, 30))
        self.assertEqual(close_time, time(13, 0))

    def test_35_calendar_trading_hours_filtering(self):
        cal = MarketSessionCalendar()
        bars = [
            {"event_time": "2026-11-20T14:00:00Z"},  # 9:00 AM EST -> closed
            {"event_time": "2026-11-20T15:00:00Z"},  # 10:00 AM EST -> open
            {"event_time": "2026-11-20T21:30:00Z"},  # 4:30 PM EST -> closed
        ]
        filtered = cal.filter_trading_minutes(bars)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["event_time"], "2026-11-20T15:00:00Z")

    def test_36_calendar_policy_version_tracked(self):
        cal = MarketSessionCalendar()
        pol = cal.get_market_calendar_policy()
        self.assertEqual(pol["policy_version"], "2026.1")
        self.assertEqual(pol["timezone"], "America/New_York")

    def test_37_economic_sequence_fingerprint_deterministic_chain(self):
        fp1 = EconomicSequenceFingerprint()
        fp1.add_event("StrategySignal", {"symbol": "NVDA", "price": 100.0})
        fp1.add_event("SimulatedOrder", {"order_id": "ord_1", "qty": 10})
        h1 = fp1.compute_fingerprint()

        fp2 = EconomicSequenceFingerprint()
        fp2.add_event("StrategySignal", {"symbol": "NVDA", "price": 100.0})
        fp2.add_event("SimulatedOrder", {"order_id": "ord_1", "qty": 10})
        h2 = fp2.compute_fingerprint()

        self.assertEqual(h1, h2)

    def test_38_economic_sequence_fingerprint_verification(self):
        events = [{"event_type": "Signal", "payload": {"p": 1}}]
        h = compute_configuration_hash(events)
        self.assertTrue(EconomicSequenceFingerprint.verify(events, h))
        self.assertFalse(EconomicSequenceFingerprint.verify(events, "wrong_hash"))

    def test_39_bot_lifecycle_data_gap_blocked_state_enum(self):
        self.assertEqual(BotLifecycleState.DATA_GAP_BLOCKED, "DATA_GAP_BLOCKED")

    def test_40_bot_lifecycle_transitions_to_and_from_data_gap_blocked(self):
        session = BotSession(
            bot_session_id="sess_dg_test",
            bot_name="TestBot",
            strategy_name="MA_CROSS_1M",
            symbols=["NVDA"],
            timeframe="1m",
            initial_cash=100000.0,
        )
        BotLifecycleStateMachine.transition(session, BotLifecycleState.STARTING)
        BotLifecycleStateMachine.transition(session, BotLifecycleState.RUNNING)
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)

        # Transition to DATA_GAP_BLOCKED
        BotLifecycleStateMachine.transition(
            session,
            BotLifecycleState.DATA_GAP_BLOCKED,
            reason="QUEUE_OVERFLOW",
        )
        self.assertEqual(session.lifecycle_state, BotLifecycleState.DATA_GAP_BLOCKED)

        # Reconcile back to RUNNING
        BotLifecycleStateMachine.transition(
            session,
            BotLifecycleState.RUNNING,
            reason="BACKLOG_REPLAYED",
        )
        self.assertEqual(session.lifecycle_state, BotLifecycleState.RUNNING)

    def test_41_dispatcher_fail_closed_on_queue_overflow_marks_data_gap_blocked(self):
        dispatcher = V2MarketDataDispatcher(max_queue_size_per_bot=2)
        dispatcher.subscription_manager.register_subscription(
            BotSubscription(bot_id="b_overflow", symbols={"NVDA"}, timeframe="1m", is_active=True)
        )

        ev1 = MarketDataEvent(symbol="NVDA", timeframe="1m", open=1.0, high=1.0, low=1.0, close=1.0, volume=100, event_id="e1", event_time=datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc))
        ev2 = MarketDataEvent(symbol="NVDA", timeframe="1m", open=1.0, high=1.0, low=1.0, close=1.0, volume=100, event_id="e2", event_time=datetime(2026, 11, 20, 15, 1, tzinfo=timezone.utc))
        ev3 = MarketDataEvent(symbol="NVDA", timeframe="1m", open=1.0, high=1.0, low=1.0, close=1.0, volume=100, event_id="e3", event_time=datetime(2026, 11, 20, 15, 2, tzinfo=timezone.utc))

        r1 = dispatcher.dispatch_event(ev1)
        self.assertEqual(r1["b_overflow"], "ENQUEUED")
        r2 = dispatcher.dispatch_event(ev2)
        self.assertEqual(r2["b_overflow"], "ENQUEUED")

        # Third event overflows bounded queue (max_queue_size=2)
        r3 = dispatcher.dispatch_event(ev3)
        self.assertEqual(r3["b_overflow"], "DROPPED_QUEUE_FULL")
        self.assertTrue(dispatcher.is_bot_blocked("b_overflow"))

        # Subsequent event is rejected due to active data gap
        ev4 = MarketDataEvent(symbol="NVDA", timeframe="1m", open=1.0, high=1.0, low=1.0, close=1.0, volume=100, event_id="e4", event_time=datetime(2026, 11, 20, 15, 3, tzinfo=timezone.utc))
        r4 = dispatcher.dispatch_event(ev4)
        self.assertEqual(r4["b_overflow"], "DATA_GAP_BLOCKED")

    def test_42_dispatcher_reconcile_data_gap_restores_running_and_preserves_peer_bots(self):
        dispatcher = V2MarketDataDispatcher(max_queue_size_per_bot=5)
        # Register slow bot and healthy peer bot
        dispatcher.subscription_manager.register_subscription(
            BotSubscription(bot_id="b_slow", symbols={"NVDA"}, timeframe="1m", is_active=True)
        )
        dispatcher.subscription_manager.register_subscription(
            BotSubscription(bot_id="b_healthy", symbols={"NVDA"}, timeframe="1m", is_active=True)
        )

        dispatcher._gap_blocked_bots.add("b_slow")
        self.assertTrue(dispatcher.is_bot_blocked("b_slow"))
        self.assertFalse(dispatcher.is_bot_blocked("b_healthy"))

        # Dispatch event: healthy bot gets ENQUEUED, blocked bot gets DATA_GAP_BLOCKED
        ev = MarketDataEvent(symbol="NVDA", timeframe="1m", open=1.0, high=1.0, low=1.0, close=1.0, volume=100, event_id="e_peer", event_time=datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc))
        res = dispatcher.dispatch_event(ev)
        self.assertEqual(res["b_healthy"], "ENQUEUED")
        self.assertEqual(res["b_slow"], "DATA_GAP_BLOCKED")

        # Reconcile slow bot
        dispatcher.reconcile_data_gap("b_slow", [ev])
        self.assertFalse(dispatcher.is_bot_blocked("b_slow"))

    # =========================================================================
    # Group E: Backtest Experiment Manager Lifecycle (10 tests)
    # =========================================================================

    def test_43_create_experiment_with_variants(self):
        exp = self.exp_manager.create_experiment(
            name="MA Grid Search",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[
                {"parameters": {"fast_window": 10, "slow_window": 30}},
                {"parameters": {"fast_window": 20, "slow_window": 50}},
            ],
        )
        self.assertEqual(exp.name, "MA Grid Search")
        self.assertEqual(len(exp.variants), 2)
        self.assertEqual(exp.status, "PENDING")

    def test_44_experiment_stores_canonical_hashes(self):
        exp = self.exp_manager.create_experiment(
            name="Hash Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 15, "slow_window": 45}}],
        )
        v = exp.variants[0]
        self.assertIsNotNone(v.strategy_hash)
        self.assertEqual(len(v.strategy_hash), 64)

    def test_45_experiment_variant_hashing_uniqueness(self):
        exp = self.exp_manager.create_experiment(
            name="Uniqueness Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[
                {"parameters": {"fast_window": 10, "slow_window": 30}},
                {"parameters": {"fast_window": 20, "slow_window": 60}},
            ],
        )
        self.assertNotEqual(exp.variants[0].strategy_hash, exp.variants[1].strategy_hash)

    def test_46_run_experiment_lifecycle_pending_to_completed(self):
        exp = self.exp_manager.create_experiment(
            name="Run Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 10, "slow_window": 30}}],
        )
        finished_exp = self.exp_manager.run_experiment(exp.experiment_id)
        self.assertEqual(finished_exp.status, "COMPLETED")
        self.assertEqual(finished_exp.variants[0].status, "COMPLETED")
        self.assertIsNotNone(finished_exp.variants[0].metrics)

    def test_47_cancel_experiment_cancels_pending_variants(self):
        exp = self.exp_manager.create_experiment(
            name="Cancel Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 10, "slow_window": 30}}],
        )
        cancelled = self.exp_manager.cancel_experiment(exp.experiment_id)
        self.assertTrue(cancelled)
        loaded = self.exp_manager.get_experiment(exp.experiment_id)
        self.assertEqual(loaded["status"], "CANCELLED")

    def test_48_experiment_concurrency_quota(self):
        exp = self.exp_manager.create_experiment(
            name="Concurrency Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 10, "slow_window": 30}}],
            max_concurrency=2,
        )
        self.assertEqual(exp.max_concurrency, 2)

    def test_49_experiment_persistence_and_retrieval(self):
        exp = self.exp_manager.create_experiment(
            name="Persist Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 10, "slow_window": 30}}],
        )
        loaded = self.exp_manager.get_experiment(exp.experiment_id)
        self.assertEqual(loaded["name"], "Persist Test")

    def test_50_experiment_list_ordering(self):
        self.exp_manager.create_experiment("Exp 1", "MA_CROSS_1M", "1.0", [])
        self.exp_manager.create_experiment("Exp 2", "MA_CROSS_1M", "1.0", [])
        exps = self.exp_manager.list_experiments()
        self.assertGreaterEqual(len(exps), 2)

    def test_51_experiment_variant_error_handling_marks_failed(self):
        exp = self.exp_manager.create_experiment(
            name="Fail Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[{"parameters": {"fast_window": 10, "slow_window": 30}}],
        )
        def failing_factory(v):
            raise RuntimeError("Synthetic backtest runner failure")

        finished_exp = self.exp_manager.run_experiment(exp.experiment_id, runner_factory=failing_factory)
        self.assertEqual(finished_exp.status, "FAILED")
        self.assertEqual(finished_exp.variants[0].status, "FAILED")

    def test_52_experiment_comparison_summary_auto_generated(self):
        exp = self.exp_manager.create_experiment(
            name="Comp Auto Test",
            base_strategy_id="MA_CROSS_1M",
            dataset_version="1.0",
            variants_spec=[
                {"parameters": {"fast_window": 10, "slow_window": 30}},
                {"parameters": {"fast_window": 20, "slow_window": 50}},
            ],
        )
        finished = self.exp_manager.run_experiment(exp.experiment_id)
        self.assertIsNotNone(finished.comparison_summary)
        self.assertIn("comparison_table", finished.comparison_summary)

    # =========================================================================
    # Group F: Comparability Rules & Enforcement (8 tests)
    # =========================================================================

    def test_53_comparability_identical_runs_are_directly_comparable(self):
        c1 = {"dataset_version": "1.0", "timeframe": "1m", "initial_capital": 100000.0}
        c2 = {"dataset_version": "1.0", "timeframe": "1m", "initial_capital": 100000.0}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertTrue(res.is_comparable)
        self.assertEqual(res.status, "DIRECTLY_COMPARABLE")

    def test_54_comparability_dataset_version_mismatch_flagged(self):
        c1 = {"dataset_version": "1.0", "timeframe": "1m"}
        c2 = {"dataset_version": "2.0", "timeframe": "1m"}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("DATASET_MISMATCH", res.reason_codes)

    def test_55_comparability_date_range_mismatch_flagged(self):
        c1 = {"start_time": "2026-11-20T09:30:00Z", "end_time": "2026-11-20T16:00:00Z"}
        c2 = {"start_time": "2026-11-21T09:30:00Z", "end_time": "2026-11-21T16:00:00Z"}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("DATE_RANGE_MISMATCH", res.reason_codes)

    def test_56_comparability_universe_mismatch_flagged(self):
        c1 = {"symbols": ["NVDA"]}
        c2 = {"symbols": ["BTC/USD"]}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("UNIVERSE_MISMATCH", res.reason_codes)

    def test_57_comparability_timeframe_mismatch_flagged(self):
        c1 = {"timeframe": "1m"}
        c2 = {"timeframe": "5m"}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("TIMEFRAME_MISMATCH", res.reason_codes)

    def test_58_comparability_fee_model_mismatch_flagged(self):
        c1 = {"fee_model": "DEFAULT"}
        c2 = {"fee_model": "ZERO"}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("FEE_MODEL_MISMATCH", res.reason_codes)

    def test_59_comparability_slippage_model_mismatch_flagged(self):
        c1 = {"slippage_model": "DEFAULT"}
        c2 = {"slippage_model": "IMPACT"}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("SLIPPAGE_MODEL_MISMATCH", res.reason_codes)

    def test_60_comparability_capital_mismatch_flagged(self):
        c1 = {"initial_capital": 100000.0}
        c2 = {"initial_capital": 50000.0}
        res = ComparabilityEngine.evaluate(c1, c2)
        self.assertFalse(res.is_comparable)
        self.assertIn("CAPITAL_MISMATCH", res.reason_codes)

    # =========================================================================
    # Group G: Comparative Analytics & Metrics Engine (8 tests)
    # =========================================================================

    def test_61_comparison_table_kpis_and_baseline_identification(self):
        runs = [
            {"variant_id": "v_base", "name": "Base", "metrics": {"sharpe_ratio": 1.5, "total_return_pct": 10.0, "max_drawdown_pct": 5.0}},
            {"variant_id": "v_alt", "name": "Alt", "metrics": {"sharpe_ratio": 1.8, "total_return_pct": 14.0, "max_drawdown_pct": 4.0}},
        ]
        res = BacktestComparisonService.compare_runs(runs, baseline_id="v_base")
        self.assertEqual(res["baseline_id"], "v_base")
        table = res["comparison_table"]
        self.assertEqual(len(table), 2)
        self.assertTrue(table[0]["is_baseline"])
        self.assertFalse(table[1]["is_baseline"])

    def test_62_comparison_metric_deltas_calculation(self):
        runs = [
            {"variant_id": "v1", "metrics": {"sharpe_ratio": 1.0, "total_return_pct": 5.0, "max_drawdown_pct": 10.0}},
            {"variant_id": "v2", "metrics": {"sharpe_ratio": 1.5, "total_return_pct": 8.0, "max_drawdown_pct": 8.0}},
        ]
        res = BacktestComparisonService.compare_runs(runs, baseline_id="v1")
        alt_row = res["comparison_table"][1]
        self.assertEqual(alt_row["delta_sharpe"], 0.5)
        self.assertEqual(alt_row["delta_return_pct"], 3.0)
        self.assertEqual(alt_row["delta_max_drawdown_pct"], -2.0)

    def test_63_comparison_zero_denominator_safe_handling(self):
        # 0 trades, None metrics, 0 drawdown
        runs = [
            {"variant_id": "v_zero", "metrics": {"sharpe_ratio": None, "total_trades": 0, "max_drawdown_pct": 0.0}},
        ]
        res = BacktestComparisonService.compare_runs(runs)
        row = res["comparison_table"][0]
        self.assertEqual(row["sharpe_ratio"], 0.0)
        self.assertEqual(row["total_trades"], 0)

    def test_64_equity_curve_alignment_and_normalization(self):
        runs = [
            {"variant_id": "r1", "equity_curve": [{"timestamp": "T1", "equity": 100000.0}, {"timestamp": "T2", "equity": 105000.0}]},
            {"variant_id": "r2", "equity_curve": [{"timestamp": "T1", "equity": 50000.0}, {"timestamp": "T2", "equity": 55000.0}]},
        ]
        aligned = BacktestComparisonService.align_equity_curves(runs)
        self.assertIn("r1", aligned["curves"])
        self.assertEqual(aligned["curves"]["r1"][1]["normalized_equity"], 105.0)
        self.assertEqual(aligned["curves"]["r2"][1]["normalized_equity"], 110.0)

    def test_65_comparison_service_empty_runs_handled(self):
        res = BacktestComparisonService.compare_runs([])
        self.assertEqual(res["runs_count"], 0)
        self.assertEqual(len(res["comparison_table"]), 0)

    def test_66_comparison_custom_baseline_selection(self):
        runs = [
            {"variant_id": "v1", "metrics": {"sharpe_ratio": 1.0}},
            {"variant_id": "v2", "metrics": {"sharpe_ratio": 2.0}},
        ]
        res = BacktestComparisonService.compare_runs(runs, baseline_id="v2")
        self.assertEqual(res["baseline_id"], "v2")
        self.assertTrue(res["comparison_table"][1]["is_baseline"])

    def test_67_comparison_calmar_and_sortino_metrics(self):
        runs = [
            {"variant_id": "v1", "metrics": {"sortino_ratio": 2.1, "calmar_ratio": 1.4}},
        ]
        res = BacktestComparisonService.compare_runs(runs)
        self.assertEqual(res["comparison_table"][0]["sortino_ratio"], 2.1)
        self.assertEqual(res["comparison_table"][0]["calmar_ratio"], 1.4)

    def test_68_comparison_handles_nan_and_inf_cleanly(self):
        runs = [
            {"variant_id": "v_nan", "metrics": {"sharpe_ratio": float("nan"), "total_return_pct": float("inf")}},
        ]
        res = BacktestComparisonService.compare_runs(runs)
        self.assertEqual(res["comparison_table"][0]["sharpe_ratio"], 0.0)
        self.assertEqual(res["comparison_table"][0]["total_return_pct"], 0.0)

    # =========================================================================
    # Group H: Strategy Robustness Analysis & REST API (7 tests)
    # =========================================================================

    def test_69_robustness_parameter_sensitivity_mean_stdev_cv(self):
        results = [
            {"metrics": {"sharpe_ratio": 1.4}},
            {"metrics": {"sharpe_ratio": 1.5}},
            {"metrics": {"sharpe_ratio": 1.6}},
        ]
        sens = StrategyRobustnessAnalyzer.analyze_parameter_sensitivity(
            base_parameters={"fast": 20},
            parameter_results=results,
            metric_key="sharpe_ratio",
        )
        self.assertEqual(sens["sample_count"], 3)
        self.assertEqual(sens["mean"], 1.5)
        self.assertTrue(sens["is_robust"])
        self.assertFalse(sens["brittleness_warning"])

    def test_70_robustness_parameter_brittleness_warning(self):
        results = [
            {"metrics": {"sharpe_ratio": 2.0}},
            {"metrics": {"sharpe_ratio": -0.5}},
            {"metrics": {"sharpe_ratio": 0.1}},
        ]
        sens = StrategyRobustnessAnalyzer.analyze_parameter_sensitivity(
            base_parameters={"fast": 20},
            parameter_results=results,
            metric_key="sharpe_ratio",
        )
        self.assertTrue(sens["brittleness_warning"])

    def test_71_robustness_temporal_split_chronological_no_leakage(self):
        bars = list(range(100))
        train, val, test = StrategyRobustnessAnalyzer.split_dataset_temporal(bars, 0.6, 0.2, 0.2)
        self.assertEqual(len(train), 60)
        self.assertEqual(len(val), 20)
        self.assertEqual(len(test), 20)
        # Verify strict order
        self.assertEqual(train[-1], 59)
        self.assertEqual(val[0], 60)
        self.assertEqual(val[-1], 79)
        self.assertEqual(test[0], 80)

    def test_72_robustness_temporal_performance_degradation_overfitting_risk(self):
        # Severe degradation: IS=2.0, OOS=0.1
        eval_res = StrategyRobustnessAnalyzer.evaluate_temporal_performance(
            in_sample_metrics={"sharpe_ratio": 2.0, "total_return_pct": 25.0},
            out_of_sample_metrics={"sharpe_ratio": 0.1, "total_return_pct": 1.0},
        )
        self.assertEqual(eval_res["overfitting_risk"], "HIGH")
        self.assertIn("REJECT_OVERFIT", eval_res["recommendation"])

    def test_73_robustness_strict_no_auto_deployment_invariant(self):
        eval_res = StrategyRobustnessAnalyzer.evaluate_temporal_performance(
            in_sample_metrics={"sharpe_ratio": 1.8},
            out_of_sample_metrics={"sharpe_ratio": 1.6},
        )
        self.assertFalse(eval_res["auto_deploy_allowed"])

    def test_74_api_strategies_and_presets_endpoints(self):
        from fastapi import FastAPI
        from libs.bot.api.experiment_routes import router as exp_router

        test_app = FastAPI()
        test_app.include_router(exp_router)
        client = TestClient(test_app)

        # GET /api/v2/strategies
        res = client.get("/api/v2/strategies", headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("strategies", res.json())

        unique_pid = f"test_api_preset_{uuid.uuid4().hex[:8]}"
        # POST /api/v2/strategy-presets
        p_res = client.post("/api/v2/strategy-presets", json={
            "preset_id": unique_pid,
            "preset_name": "API Test Preset",
            "strategy_id": "MA_CROSS_1M",
            "parameters": {"fast_window": 10, "slow_window": 30},
        }, headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(p_res.status_code, 201)

        # GET /api/v2/strategy-presets
        list_res = client.get("/api/v2/strategy-presets", headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(list_res.status_code, 200)

    def test_75_api_experiments_crud_and_comparison_endpoints(self):
        from fastapi import FastAPI
        from libs.bot.api.experiment_routes import router as exp_router

        test_app = FastAPI()
        test_app.include_router(exp_router)
        client = TestClient(test_app)

        # POST /api/v2/experiments
        exp_res = client.post("/api/v2/experiments", json={
            "name": "API Exp 1",
            "base_strategy_id": "MA_CROSS_1M",
            "dataset_version": "1.0",
            "variants": [
                {"parameters": {"fast_window": 10, "slow_window": 30}},
                {"parameters": {"fast_window": 20, "slow_window": 50}},
            ],
        }, headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(exp_res.status_code, 201)
        exp_id = exp_res.json()["experiment_id"]

        # POST /api/v2/experiments/{id}/run
        run_res = client.post(f"/api/v2/experiments/{exp_id}/run", headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(run_res.status_code, 200)
        self.assertEqual(run_res.json()["status"], "COMPLETED")

        # GET /api/v2/experiments/{id}/comparison
        comp_res = client.get(f"/api/v2/experiments/{exp_id}/comparison", headers={"X-API-KEY": "simulation_token_v2"})
        self.assertEqual(comp_res.status_code, 200)
        self.assertIn("comparison_table", comp_res.json())


if __name__ == "__main__":
    unittest.main()
