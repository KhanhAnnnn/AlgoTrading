"""
libs/bot/orchestration/orchestrator.py — Master Bot Orchestrator (GĐ34)
Central controller coordinating Data Layer, Strategy Engine, Portfolio & Risk Engine,
Simulation Broker, Event Loop, Checkpoints, Health, and Performance Reporting.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    BotAuditEvent,
)
from libs.bot.orchestration.lifecycle import (
    BotLifecycleState,
    BotLifecycleStateMachine,
    InvalidLifecycleStateTransitionError,
)
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.event_journal import BotEventJournal
from libs.bot.orchestration.checkpoint import BotCheckpointManager, BotCheckpoint
from libs.bot.orchestration.health import BotHealthMonitor
from libs.bot.orchestration.performance import BotPerformanceReporter
from libs.bot.orchestration.event_loop import BotEventLoop
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.execution.simulation_broker import SimulationBroker

logger = logging.getLogger("bot-orchestrator")


class BotOrchestrator:
    """
    Master orchestrator for Paper Trading Bot V2.
    Runs entirely within an isolated simulation sandbox with zero external broker calls.
    """

    def __init__(
        self,
        session: BotSession,
        portfolio: SimulationPortfolioManager,
        risk_config: RiskConfig,
        strategy_engine: StrategyExecutionEngine,
        simulation_broker: SimulationBroker,
        session_store: Optional[SessionStore] = None,
        checkpoint_manager: Optional[BotCheckpointManager] = None,
        journal: Optional[BotEventJournal] = None,
        stop_policy: StopPolicy = StopPolicy.CANCEL_REMAINDER,
        max_queue_size: int = 1000,
    ):
        self.session = session
        self.portfolio = portfolio
        self.risk_config = risk_config
        self.strategy_engine = strategy_engine
        self.simulation_broker = simulation_broker
        self.stop_policy = stop_policy

        self.session_store = session_store or SessionStore()
        self.checkpoint_manager = checkpoint_manager or BotCheckpointManager()
        self.journal = journal or BotEventJournal(self.session.bot_session_id)
        self.health_monitor = BotHealthMonitor(self.session.bot_session_id)
        self.performance_reporter = BotPerformanceReporter(self.session.bot_session_id)

        # Wire Decision Engine
        self.decision_engine = SignalDecisionEngine(
            portfolio=self.portfolio,
            config=self.risk_config,
        )

        # Wire Event Loop
        self.event_loop = BotEventLoop(
            strategy_engine=self.strategy_engine,
            decision_engine=self.decision_engine,
            simulation_broker=self.simulation_broker,
            journal=self.journal,
            health_monitor=self.health_monitor,
            max_queue_size=max_queue_size,
        )

        # Update hashes
        self.session.risk_config_hash = self.risk_config.compute_hash()
        self.session_store.save_session(self.session)

    @property
    def broker(self) -> SimulationBroker:
        return self.simulation_broker

    @property
    def risk_engine(self) -> SignalDecisionEngine:
        return self.decision_engine

    @property
    def state(self) -> str:
        return self.session.lifecycle_state

    def on_market_data(self, bar: MarketDataEvent) -> Optional[Dict[str, Any]]:
        """Compatibility alias for submit_bar."""
        return self.submit_bar(bar)

    def start(self) -> bool:
        """
        Starts the bot session: STARTING -> RUNNING.
        Enables event processing.
        """
        try:
            if self.session.lifecycle_state == BotLifecycleState.STOPPED:
                # Transition through STARTING first
                BotLifecycleStateMachine.transition(self.session, BotLifecycleState.STARTING, reason="Initializing services")
            BotLifecycleStateMachine.transition(self.session, BotLifecycleState.RUNNING, reason="Event loop started")
            self.event_loop.is_paused = False
            self.health_monitor.lifecycle_state = BotLifecycleState.RUNNING
            self.session_store.save_session(self.session)
            logger.info(f"Bot session {self.session.bot_session_id} successfully started (RUNNING)")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot session: {e}")
            self.handle_error("START_FAILED", str(e))
            return False

    def pause(self, reason: str = "OPERATOR_REQUESTED") -> bool:
        """
        Pauses the bot session: RUNNING -> PAUSED.
        Suspends event loop processing without cancelling active orders.
        """
        try:
            BotLifecycleStateMachine.transition(self.session, BotLifecycleState.PAUSED, reason=reason)
            self.event_loop.is_paused = True
            self.health_monitor.lifecycle_state = BotLifecycleState.PAUSED
            self.save_checkpoint()
            self.session_store.save_session(self.session)
            logger.info(f"Bot session {self.session.bot_session_id} PAUSED ({reason})")
            return True
        except Exception as e:
            logger.error(f"Failed to pause bot: {e}")
            self.handle_error("PAUSE_FAILED", str(e))
            return False

    def resume(self) -> bool:
        """
        Resumes the bot session: PAUSED -> RUNNING.
        Reactivates event loop processing.
        """
        try:
            BotLifecycleStateMachine.transition(self.session, BotLifecycleState.RUNNING, reason="Resumed by operator")
            self.event_loop.is_paused = False
            self.health_monitor.lifecycle_state = BotLifecycleState.RUNNING
            self.session_store.save_session(self.session)
            logger.info(f"Bot session {self.session.bot_session_id} RESUMED (RUNNING)")
            return True
        except Exception as e:
            logger.error(f"Failed to resume bot: {e}")
            self.handle_error("RESUME_FAILED", str(e))
            return False

    def stop(self, policy: Optional[StopPolicy] = None, reason: str = "SHUTDOWN_REQUESTED") -> bool:
        """
        Executes graceful shutdown: RUNNING/PAUSED -> STOPPING -> STOPPED.
        Applies StopPolicy to open simulation orders and flushes state.
        """
        try:
            eff_policy = policy or self.stop_policy
            BotLifecycleStateMachine.transition(self.session, BotLifecycleState.STOPPING, reason=reason)
            self.event_loop.is_paused = True
            self.health_monitor.lifecycle_state = BotLifecycleState.STOPPING

            # 1. Apply Stop Policy to open orders in Simulation Broker
            if eff_policy == StopPolicy.CANCEL_REMAINDER:
                open_orders = self.simulation_broker.order_manager.get_open_orders()
                for o in open_orders:
                    self.simulation_broker.cancel_order(o.simulated_order_id, reason="BOT_SHUTDOWN")

            # 2. Reconcile
            rec = self.simulation_broker.reconcile()
            self.health_monitor.reconciliation_status = rec.status

            # 3. Save Checkpoint & Performance Report
            self.save_checkpoint()
            self.get_performance_report()

            # 4. Transition to STOPPED terminal state
            BotLifecycleStateMachine.transition(self.session, BotLifecycleState.STOPPED, reason="Shutdown completed")
            self.health_monitor.lifecycle_state = BotLifecycleState.STOPPED
            self.session_store.save_session(self.session)
            logger.info(f"Bot session {self.session.bot_session_id} STOPPED successfully")
            return True
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")
            self.handle_error("STOP_FAILED", str(e))
            return False

    def handle_error(self, error_code: str, error_message: str) -> None:
        """
        Transitions session to ERROR state and persists diagnostic context.
        """
        try:
            BotLifecycleStateMachine.transition(
                self.session,
                BotLifecycleState.ERROR,
                reason=error_message,
                error_code=error_code,
                error_message=error_message,
            )
            self.event_loop.is_paused = True
            self.health_monitor.lifecycle_state = BotLifecycleState.ERROR
            self.health_monitor.record_error(f"{error_code}: {error_message}")
            self.session_store.save_session(self.session)
        except Exception as e:
            logger.critical(f"Catastrophic failure in error handler: {e}")

    def submit_bar(self, bar: MarketDataEvent, auto_process: bool = True) -> Optional[Dict[str, Any]]:
        """
        Submits an incoming 1m market data event to the bot event loop.
        If auto_process is True, synchronously executes the next event in the queue.
        """
        if self.session.lifecycle_state != BotLifecycleState.RUNNING:
            logger.debug(f"Rejecting bar {bar.bar_key}: bot is in state '{self.session.lifecycle_state}'")
            return None

        # Check feed freshness
        if self.health_monitor.check_feed_staleness():
            logger.warning("Feed staleness detected; processing with degraded health warning")

        enqueued = self.event_loop.enqueue_event(bar)
        if not enqueued:
            return None

        if auto_process:
            res = self.event_loop.process_next_event()
            if res and res.get("status") == "PROCESSED":
                self.session.last_processed_bar_key = bar.bar_key
                self.session.last_processed_event_id = bar.event_id
                self.session_store.save_session(self.session)
            return res
        return {"status": "ENQUEUED", "bar_key": bar.bar_key}

    def save_checkpoint(self) -> BotCheckpoint:
        """Creates and persists an atomic checkpoint."""
        snap = self.portfolio.get_portfolio_snapshot()
        rec = self.simulation_broker.reconcile()

        cp = self.checkpoint_manager.save_checkpoint(
            bot_session_id=self.session.bot_session_id,
            consumer_group=self.session.data_consumer_group,
            partition_offsets={"stocks": 0, "crypto": 0},
            last_processed_event_id=self.session.last_processed_event_id,
            last_processed_bar_key=self.session.last_processed_bar_key,
            portfolio_snapshot_id=snap.snapshot_id,
            reconciliation_status=rec.status,
            configuration_hash=self.session.risk_config_hash,
        )
        self.session.checkpoint_id = cp.checkpoint_id
        return cp

    def get_performance_report(self) -> Dict[str, Any]:
        """Compiles and persists session performance metrics."""
        orders = list(self.simulation_broker.order_manager._orders.values())
        fills = self.simulation_broker._fills
        telemetry = self.decision_engine.telemetry

        return self.performance_reporter.generate_report(
            session=self.session,
            portfolio=self.portfolio,
            orders=orders,
            fills=fills,
            signals_received=telemetry.get("signals_received", 0),
            signals_accepted=telemetry.get("decisions_accepted", 0),
            signals_rejected=telemetry.get("decisions_rejected", 0),
        )

    def get_health(self) -> Dict[str, Any]:
        """Returns health status."""
        return self.health_monitor.get_health_status()
