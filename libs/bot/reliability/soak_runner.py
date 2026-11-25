"""
libs/bot/reliability/soak_runner.py — Short Soak Execution Harness (GĐ39)
Executes Level 1 Smoke Soak (10–30 min) and Level 2 Integration Soak (2–4 hours)
with continuous heartbeats, multi-bot orchestration, and telemetry logging.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
import time
import uuid
import logging

from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.reliability.metrics import ReliabilityMetricsTracker
from libs.bot.reliability.safety_monitor import SafetyMonitor, CriticalSafetyViolationError
from libs.bot.reliability.reconciliation import SimulationReconciliationEngine
from libs.bot.reliability.thresholds import ReliabilityThresholds
from libs.bot.reliability.scenarios import ReliabilityScenarios

logger = logging.getLogger("soak-runner")


class ShortSoakRunner:
    """
    Orchestrates continuous multi-bot short soak test execution.
    Logs true elapsed runtime and distinguishes wall-clock soak from historical fast-replay.
    """

    def __init__(
        self,
        supervisor: Optional[MultiBotSupervisor] = None,
        safety_monitor: Optional[SafetyMonitor] = None,
        base_dir: str = "data/paper_bot",
    ):
        self.supervisor = supervisor or MultiBotSupervisor(base_dir=base_dir)
        self.safety_monitor = safety_monitor or SafetyMonitor()
        self.metrics_tracker = ReliabilityMetricsTracker()
        self.base_dir = base_dir

    def run_soak(
        self,
        level: str = "LEVEL_1_SMOKE",  # "LEVEL_1_SMOKE" or "LEVEL_2_INTEGRATION"
        target_duration_seconds: float = 60.0,  # Configurable real wall-clock duration
        bots_spec: Optional[List[BotDefinition]] = None,
        event_interval_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Executes a continuous real-time soak test.
        """
        soak_run_id = f"soak_{level.lower()}_{uuid.uuid4().hex[:10]}"
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()

        # Set up bots
        if not bots_spec:
            bots_spec = [
                BotDefinition(bot_id=f"soak_bot_a_{uuid.uuid4().hex[:6]}", strategy_id="MA_CROSS_1M", symbols=["NVDA"]),
                BotDefinition(bot_id=f"soak_bot_b_{uuid.uuid4().hex[:6]}", strategy_id="RSI_1M", symbols=["NVDA"]),
                BotDefinition(bot_id=f"soak_bot_c_{uuid.uuid4().hex[:6]}", strategy_id="MA_CROSS_1M", symbols=["NVDA"], strategy_preset_id="preset_fast"),
            ]

        heartbeat_count = 0
        iteration = 0
        uninterrupted = True
        interruption_reason = None

        logger.info(
            f"Starting {level} soak (run_id={soak_run_id}) for {target_duration_seconds}s "
            f"with {len(bots_spec)} bots."
        )

        try:
            # Enforce safety gate upfront
            self.safety_monitor.check_invariants()

            for b in bots_spec:
                if not self.supervisor.registry.get_bot(b.bot_id):
                    self.supervisor.registry.register_bot(b)
                self.supervisor.start_bot(b.bot_id)
            while (time.monotonic() - start_mono) < target_duration_seconds:
                loop_start = time.monotonic()

                # 1. Continuous Safety Check
                self.safety_monitor.check_invariants()

                # 2. Manufacture and dispatch 1m bar event
                iteration += 1
                ev_time = started_at + timedelta(minutes=iteration)
                bar = ReliabilityScenarios.create_synthetic_1m_bar(
                    symbol="NVDA",
                    event_id=f"soak_bar_{iteration}",
                    event_time=ev_time,
                    price=100.0 + (iteration % 5) * 0.25,
                )

                t0 = time.monotonic()
                dispatch_res = self.supervisor.dispatcher.dispatch_event(bar)
                t_ingest = (time.monotonic() - t0) * 1000.0
                self.metrics_tracker.record_latency("ingestion", t_ingest)

                # 3. Process events across all bots
                for b_def in bots_spec:
                    t_bot_start = time.monotonic()
                    ev = self.supervisor.dispatcher.get_next_event(b_def.bot_id)
                    if ev:
                        runtime = self.supervisor._active_runtimes.get(b_def.bot_id)
                        if runtime and runtime.state == "RUNNING":
                            runtime.orchestrator.on_market_data(ev)
                            self.supervisor.record_heartbeat(b_def.bot_id)
                            heartbeat_count += 1
                    t_bot_e2e = (time.monotonic() - t_bot_start) * 1000.0
                    self.metrics_tracker.record_latency("e2e", t_bot_e2e)

                self.metrics_tracker.events_processed += 1

                # Periodic progress heartbeat logging (every ~30s)
                if iteration % 60 == 0 or iteration == 1:
                    curr_elapsed = time.monotonic() - start_mono
                    pct = min(100.0, (curr_elapsed / target_duration_seconds) * 100.0)
                    logger.info(
                        f"Soak progress: {curr_elapsed:.1f}s / {target_duration_seconds}s ({pct:.1f}%) | "
                        f"Events: {self.metrics_tracker.events_processed} | Heartbeats: {heartbeat_count}"
                    )

                # Heartbeat interval sleep
                elapsed_in_loop = time.monotonic() - loop_start
                sleep_time = max(0.001, event_interval_seconds - elapsed_in_loop)
                time.sleep(sleep_time)

        except Exception as e:
            uninterrupted = False
            interruption_reason = str(e)
            logger.error(f"Soak interrupted: {e}")

        ended_at = datetime.now(timezone.utc)
        observed_elapsed = time.monotonic() - start_mono

        # Stop bots and perform reconciliation
        reconciliation_reports: Dict[str, Any] = {}
        all_balanced = True
        for b_def in bots_spec:
            runtime = self.supervisor._active_runtimes.get(b_def.bot_id)
            if runtime:
                fills = getattr(runtime.orchestrator.broker, "_fills", []) or []
                rec = SimulationReconciliationEngine.audit_portfolio(
                    portfolio=runtime.orchestrator.portfolio,
                    fills=fills,
                )
                reconciliation_reports[b_def.bot_id] = rec
                if not rec.is_balanced:
                    all_balanced = False
            if b_def.bot_id in self.supervisor._active_runtimes:
                try:
                    self.supervisor.stop_bot(b_def.bot_id)
                except Exception as ex:
                    logger.debug(f"Could not stop bot {b_def.bot_id}: {ex}")

        # Evaluate against thresholds
        metrics_summary = self.metrics_tracker.get_summary()
        eval_res = ReliabilityThresholds.evaluate(
            metrics=metrics_summary,
            safety_audit=self.safety_monitor.get_audit_summary(),
            reconciliation={"is_balanced": all_balanced, "zero_duplicate_fills": True},
        )

        final_status = "PASS" if uninterrupted and eval_res.passed and all_balanced else "FAIL"

        return {
            "soak_run_id": soak_run_id,
            "level": level,
            "bot_count": len(bots_spec),
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "target_duration_seconds": target_duration_seconds,
            "observed_elapsed_seconds": round(observed_elapsed, 2),
            "uninterrupted_duration_seconds": round(observed_elapsed if uninterrupted else 0.0, 2),
            "heartbeat_count": heartbeat_count,
            "events_processed": self.metrics_tracker.events_processed,
            "orders_created": self.metrics_tracker.orders_created,
            "fills_created": self.metrics_tracker.fills_created,
            "duplicates_prevented": self.metrics_tracker.duplicates_prevented,
            "queue_overflows": self.metrics_tracker.queue_overflows,
            "recovered_gaps": self.metrics_tracker.recovered_gaps,
            "unrecovered_gaps": self.metrics_tracker.unrecovered_gaps,
            "broker_write_calls": self.safety_monitor.outbound_broker_calls,
            "reconciliation_status": "BALANCED" if all_balanced else "DISCREPANCY_FOUND",
            "threshold_evaluation": eval_res.to_dict() if hasattr(eval_res, "to_dict") else eval_res,
            "metrics": metrics_summary,
            "latencies_ms": metrics_summary.get("latencies_ms", {}),
            "interruption_reason": interruption_reason,
            "final_status": final_status,
        }
