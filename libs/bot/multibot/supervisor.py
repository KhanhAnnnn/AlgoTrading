"""
libs/bot/multibot/supervisor.py — Multi-Bot Central Supervisor (GĐ37)
Orchestrates multiple concurrent Paper Trading Bots, manages independent runtimes,
enforces concurrency limits, aggregates health, and isolates failures.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging

from libs.bot.domain import MarketDataEvent, BotSession, PortfolioSnapshot
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.resource_policy import ResourcePolicy, ConcurrencyLimitExceededError
from libs.bot.multibot.subscriptions import SubscriptionManager, BotSubscription
from libs.bot.multibot.dispatcher import V2MarketDataDispatcher
from libs.bot.multibot.isolation import BotSandboxFactory
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.lifecycle import BotLifecycleState
from libs.bot.orchestration.stop_policy import StopPolicy

logger = logging.getLogger("multibot-supervisor")


class BotNotFoundError(KeyError):
    """Raised when requesting an unregistered bot ID."""
    pass


@dataclass
class BotRuntime:
    """Container holding runtime state for an active BotOrchestrator."""
    definition: BotDefinition
    session: BotSession
    orchestrator: BotOrchestrator
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None

    @property
    def bot_id(self) -> str:
        return self.definition.bot_id

    @property
    def session_id(self) -> str:
        return self.session.bot_session_id

    @property
    def state(self) -> str:
        return self.orchestrator.state


class MultiBotSupervisor:
    """
    Master Supervisor orchestrating concurrent simulation bots.
    Maintains independent runtimes, enforces resource limits, and guarantees failure isolation.
    """

    def __init__(
        self,
        registry: Optional[BotRegistry] = None,
        dispatcher: Optional[V2MarketDataDispatcher] = None,
        subscription_manager: Optional[SubscriptionManager] = None,
        resource_policy: Optional[ResourcePolicy] = None,
        base_dir: str = "data/paper_bot",
    ):
        self.base_dir = base_dir
        self.registry = registry or BotRegistry(storage_dir=f"{base_dir}/registry")
        self.subscription_manager = subscription_manager or SubscriptionManager()
        self.resource_policy = resource_policy or ResourcePolicy()
        self.resource_policy.validate()

        self.dispatcher = dispatcher or V2MarketDataDispatcher(
            subscription_manager=self.subscription_manager,
            max_queue_size_per_bot=self.resource_policy.max_queue_size_per_bot,
        )
        self.dispatcher.set_overflow_callback(self._handle_dispatcher_overflow)

        # Active runtimes keyed by bot_id
        self._active_runtimes: Dict[str, BotRuntime] = {}

    def _handle_dispatcher_overflow(self, bot_id: str, event: Any) -> None:
        """Fail-closed isolation: transitions overflowing bot to DATA_GAP_BLOCKED."""
        runtime = self._active_runtimes.get(bot_id)
        if runtime and runtime.session:
            if runtime.session.lifecycle_state == BotLifecycleState.RUNNING:
                try:
                    from libs.bot.orchestration.lifecycle import BotLifecycleStateMachine
                    BotLifecycleStateMachine.transition(
                        runtime.session,
                        BotLifecycleState.DATA_GAP_BLOCKED,
                        reason="DROPPED_QUEUE_FULL: Data gap detected, fail-closed isolation triggered",
                        error_code="DATA_GAP_BLOCKED",
                    )
                    logger.warning(
                        f"Supervisor transitioned bot '{bot_id}' to DATA_GAP_BLOCKED due to queue overflow."
                    )
                except Exception as e:
                    logger.error(f"Failed to transition bot '{bot_id}' to DATA_GAP_BLOCKED: {e}")

    @property
    def active_bot_count(self) -> int:
        """Returns number of currently active bot runtimes."""
        return len(self._active_runtimes)

    def start_bot(
        self,
        bot_id: str,
        session_id: Optional[str] = None,
        stop_policy: StopPolicy = StopPolicy.CANCEL_REMAINDER,
    ) -> BotSession:
        """
        Starts a registered bot into RUNNING state.
        Enforces max_concurrent_bots limit.
        Idempotent if already RUNNING.
        """
        bot_def = self.registry.get_bot(bot_id)
        if not bot_def:
            raise BotNotFoundError(f"Bot '{bot_id}' is not registered")
        if bot_def.archived:
            raise ValueError(f"Bot '{bot_id}' is archived and cannot be started")
        if not bot_def.enabled:
            raise ValueError(f"Bot '{bot_id}' is disabled")

        # 1. Check if already active
        runtime = self._active_runtimes.get(bot_id)
        if runtime:
            if runtime.state == BotLifecycleState.RUNNING:
                logger.info(f"Bot '{bot_id}' is already RUNNING (session {runtime.session_id})")
                return runtime.session
            if runtime.state == BotLifecycleState.PAUSED:
                runtime.orchestrator.resume()
                runtime.last_heartbeat = datetime.now(timezone.utc)
                return runtime.session

        # 2. Apply pending preset if configured before starting
        if bot_def.pending_preset:
            p_data = bot_def.pending_preset
            if "preset_id" in p_data:
                bot_def.strategy_preset_id = p_data["preset_id"]
            if "version" in p_data:
                bot_def.strategy_config_version = p_data["version"]
            bot_def.pending_preset = None
            bot_def.configuration_hash = bot_def.compute_configuration_hash()
            self.registry.save_to_disk()
            logger.info(f"Applied pending preset to bot '{bot_id}' on session start.")

        # 3. Enforce concurrency limits
        if len(self._active_runtimes) >= self.resource_policy.max_concurrent_bots:
            raise ConcurrencyLimitExceededError(
                f"Maximum concurrent bots limit ({self.resource_policy.max_concurrent_bots}) reached"
            )

        # 4. Create isolated sandbox
        sandbox = BotSandboxFactory.create_sandbox(
            definition=bot_def,
            session_id=session_id,
            base_dir=self.base_dir,
            stop_policy=stop_policy,
            max_queue_size=self.resource_policy.max_queue_size_per_bot,
        )
        orchestrator: BotOrchestrator = sandbox["orchestrator"]
        session: BotSession = sandbox["session"]

        # 4. Register subscription with dispatcher
        sub = BotSubscription(
            bot_id=bot_id,
            symbols=set(bot_def.symbols),
            timeframe=bot_def.timeframe,
            is_active=True,
        )
        self.subscription_manager.register_subscription(sub)
        self.dispatcher.register_bot(bot_id)

        # 5. Start orchestrator
        started = orchestrator.start()
        if not started:
            raise RuntimeError(f"Failed to start orchestrator for bot '{bot_id}'")

        # 6. Store runtime
        runtime = BotRuntime(
            definition=bot_def,
            session=session,
            orchestrator=orchestrator,
            last_heartbeat=datetime.now(timezone.utc),
        )
        self._active_runtimes[bot_id] = runtime
        logger.info(f"MultiBotSupervisor started bot '{bot_id}' (session={session.bot_session_id})")
        return session

    def pause_bot(self, bot_id: str, reason: str = "SUPERVISOR_PAUSE") -> BotSession:
        """Pauses a running bot. Preserves pending working simulation orders."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")

        if runtime.state == BotLifecycleState.STOPPED:
            raise ValueError(f"Cannot pause bot '{bot_id}' in state 'STOPPED'")

        paused = runtime.orchestrator.pause(reason=reason)
        if not paused:
            raise RuntimeError(f"Failed to pause bot '{bot_id}'")

        runtime.last_heartbeat = datetime.now(timezone.utc)
        logger.info(f"MultiBotSupervisor paused bot '{bot_id}'")
        return runtime.session

    def resume_bot(self, bot_id: str) -> BotSession:
        """Resumes a paused bot."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")

        if runtime.state != BotLifecycleState.PAUSED:
            raise ValueError(f"Cannot resume bot '{bot_id}' from state '{runtime.state}'")

        resumed = runtime.orchestrator.resume()
        if not resumed:
            raise RuntimeError(f"Failed to resume bot '{bot_id}'")

        runtime.last_heartbeat = datetime.now(timezone.utc)
        logger.info(f"MultiBotSupervisor resumed bot '{bot_id}'")
        return runtime.session

    def stop_bot(
        self,
        bot_id: str,
        policy: Optional[StopPolicy] = None,
        reason: str = "SUPERVISOR_STOP",
    ) -> BotSession:
        """Stops an active bot gracefully and removes it from active runtimes."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")

        # Stop orchestrator
        stopped = runtime.orchestrator.stop(policy=policy, reason=reason)
        if not stopped:
            logger.warning(f"Stop command returned false for bot '{bot_id}', proceeding with cleanup")

        # Clean up dispatcher & subscriptions
        self.subscription_manager.remove_subscription(bot_id)
        self.dispatcher.deregister_bot(bot_id)

        # Remove from active runtimes
        self._active_runtimes.pop(bot_id, None)
        logger.info(f"MultiBotSupervisor stopped bot '{bot_id}' (session={runtime.session_id})")
        return runtime.session

    def stop_all_bots(
        self,
        policy: Optional[StopPolicy] = None,
        reason: str = "SUPERVISOR_SHUTDOWN_ALL",
        timeout: float = 5.0,
    ) -> Dict[str, str]:
        """Gracefully shuts down all active bots."""
        results: Dict[str, str] = {}
        active_ids = list(self._active_runtimes.keys())
        for b_id in active_ids:
            try:
                self.stop_bot(b_id, policy=policy, reason=reason)
                results[b_id] = "STOPPED"
            except Exception as e:
                logger.error(f"Error stopping bot '{b_id}': {e}")
                results[b_id] = f"ERROR: {e}"
        return results

    def dispatch_market_data(
        self,
        event: MarketDataEvent,
        auto_process: bool = True,
    ) -> Dict[str, Any]:
        """
        Dispatches incoming market data bar to all subscribed bots with strict failure isolation.
        If one bot encounters an exception during processing, it is isolated in ERROR state,
        allowing other bots to proceed unimpeded.
        """
        dispatch_results = self.dispatcher.dispatch_event(event)
        processing_results: Dict[str, Any] = {}

        for bot_id, status in dispatch_results.items():
            if status != "ENQUEUED":
                processing_results[bot_id] = {"dispatch_status": status}
                continue

            runtime = self._active_runtimes.get(bot_id)
            if not runtime:
                processing_results[bot_id] = {"dispatch_status": "NO_ACTIVE_RUNTIME"}
                continue

            if auto_process:
                # Drain the event from dispatcher queue and submit to orchestrator
                queued_event = self.dispatcher.get_next_event(bot_id)
                if queued_event:
                    try:
                        res = runtime.orchestrator.submit_bar(queued_event, auto_process=True)
                        self.dispatcher.ack_event(bot_id, queued_event.event_id)
                        runtime.last_heartbeat = datetime.now(timezone.utc)
                        processing_results[bot_id] = {
                            "dispatch_status": "PROCESSED",
                            "orchestrator_result": res,
                        }
                    except Exception as e:
                        # Failure isolation: single bot error does not crash peer bots
                        logger.error(f"Failure processing event for bot '{bot_id}': {e}")
                        runtime.orchestrator.handle_error("DISPATCH_EXEC_ERROR", str(e))
                        runtime.error = str(e)
                        processing_results[bot_id] = {
                            "dispatch_status": "ERROR",
                            "error": str(e),
                        }
            else:
                processing_results[bot_id] = {"dispatch_status": "ENQUEUED"}

        return processing_results

    def submit_bar_to_bot(
        self,
        bot_id: str,
        bar: MarketDataEvent,
        auto_process: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Submits a bar directly to a specific active bot."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")
        res = runtime.orchestrator.submit_bar(bar, auto_process=auto_process)
        runtime.last_heartbeat = datetime.now(timezone.utc)
        return res

    def get_bot_runtime(self, bot_id: str) -> Optional[BotRuntime]:
        """Retrieves active runtime for a bot."""
        return self._active_runtimes.get(bot_id)

    def get_bot_status(self, bot_id: str) -> Dict[str, Any]:
        """Returns comprehensive status for a bot (active or from registry/sessions)."""
        runtime = self._active_runtimes.get(bot_id)
        if runtime:
            snap = runtime.orchestrator.portfolio.get_portfolio_snapshot()
            return {
                "bot_id": bot_id,
                "session_id": runtime.session_id,
                "bot_name": runtime.definition.bot_name,
                "strategy_id": runtime.definition.strategy_id,
                "strategy_version": runtime.definition.strategy_version,
                "symbols": runtime.definition.symbols,
                "timeframe": runtime.definition.timeframe,
                "lifecycle_state": runtime.state,
                "status": runtime.state,
                "last_heartbeat": runtime.last_heartbeat.isoformat(),
                "cash": float(snap.cash),
                "equity": float(snap.equity),
                "unrealized_pnl": float(snap.unrealized_pnl),
                "realized_pnl": float(snap.realized_pnl),
                "positions_count": len(snap.positions),
                "is_active": True,
            }

        # Query definition
        bot_def = self.registry.get_bot(bot_id)
        if not bot_def:
            raise BotNotFoundError(f"Bot '{bot_id}' not found")

        # Query latest session
        past_sessions = self.registry.list_sessions_for_bot(bot_id)
        latest_session = past_sessions[0] if past_sessions else None

        return {
            "bot_id": bot_id,
            "session_id": latest_session.bot_session_id if latest_session else None,
            "bot_name": bot_def.bot_name,
            "strategy_id": bot_def.strategy_id,
            "strategy_version": bot_def.strategy_version,
            "symbols": bot_def.symbols,
            "timeframe": bot_def.timeframe,
            "lifecycle_state": latest_session.lifecycle_state if latest_session else "UNINITIALIZED",
            "status": latest_session.status if latest_session else "STOPPED",
            "last_heartbeat": None,
            "cash": float(latest_session.initial_cash) if latest_session else float(bot_def.initial_simulated_cash),
            "equity": float(latest_session.initial_cash) if latest_session else float(bot_def.initial_simulated_cash),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "positions_count": 0,
            "is_active": False,
        }

    def get_bot_portfolio(self, bot_id: str) -> Optional[PortfolioSnapshot]:
        """Returns portfolio snapshot for an active bot."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            return None
        return runtime.orchestrator.portfolio.get_portfolio_snapshot()

    def get_bot_performance(self, bot_id: str) -> Dict[str, Any]:
        """Returns performance report for a bot."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")
        return runtime.orchestrator.get_performance_report()

    def get_bot_health(self, bot_id: str) -> Dict[str, Any]:
        """Returns health monitor status for a bot."""
        runtime = self._active_runtimes.get(bot_id)
        if not runtime:
            raise BotNotFoundError(f"Bot '{bot_id}' is not currently active")
        return runtime.orchestrator.get_health()

    def get_supervisor_health(self) -> Dict[str, Any]:
        """Aggregates system-wide supervisor status, concurrency utilization, and bot health."""
        active_count = len(self._active_runtimes)
        max_allowed = self.resource_policy.max_concurrent_bots
        utilization = (active_count / max_allowed) if max_allowed > 0 else 0.0

        bot_states = {b_id: r.state for b_id, r in self._active_runtimes.items()}
        has_error = any(s == BotLifecycleState.ERROR for s in bot_states.values())

        status = "HEALTHY"
        if has_error:
            status = "DEGRADED"
        if utilization >= 1.0:
            status = "MAX_CAPACITY"

        return {
            "status": status,
            "active_bots_count": active_count,
            "max_concurrent_bots": max_allowed,
            "concurrency_utilization": round(utilization, 4),
            "bot_states": bot_states,
            "dispatcher": self.dispatcher.get_telemetry(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": "SIMULATION",
            "trading_mode": "DRY_RUN",
            "paper_execution_gate": "CLOSED",
        }

    def record_heartbeat(self, bot_id: str) -> None:
        """Updates heartbeat timestamp for an active bot."""
        runtime = self._active_runtimes.get(bot_id)
        if runtime:
            runtime.last_heartbeat = datetime.now(timezone.utc)

    def request_bot_configuration_update(
        self, bot_id: str, preset_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Updates bot configuration. If the bot is RUNNING, the update is queued as pending_preset
        and will NOT mutate the running session in place.
        """
        bot_def = self.registry.get_bot(bot_id)
        if not bot_def:
            raise BotNotFoundError(f"Bot '{bot_id}' is not registered")

        runtime = self._active_runtimes.get(bot_id)
        is_running = runtime is not None and runtime.state == BotLifecycleState.RUNNING

        if is_running:
            bot_def.pending_preset = preset_data
            self.registry.save_to_disk()
            logger.info(f"Bot '{bot_id}' is RUNNING. Preset update queued as pending_preset.")
            return {
                "status": "QUEUED_PENDING",
                "message": "Bot is RUNNING; preset update will apply upon next session start.",
            }
        else:
            if "preset_id" in preset_data:
                bot_def.strategy_preset_id = preset_data["preset_id"]
            if "version" in preset_data:
                bot_def.strategy_config_version = preset_data["version"]
            bot_def.configuration_hash = bot_def.compute_configuration_hash()
            self.registry.save_to_disk()
            return {
                "status": "APPLIED_IMMEDIATELY",
                "message": "Preset updated successfully.",
            }

    def reconcile_bot_gap(self, bot_id: str, missing_events: List[Any]) -> bool:
        """
        Reconciles a data gap by replaying backlog events into the dispatcher,
        and transitions bot back to RUNNING if it was in DATA_GAP_BLOCKED.
        """
        self.dispatcher.reconcile_data_gap(bot_id, missing_events)
        runtime = self._active_runtimes.get(bot_id)
        if runtime and runtime.session and runtime.session.lifecycle_state == BotLifecycleState.DATA_GAP_BLOCKED:
            from libs.bot.orchestration.lifecycle import BotLifecycleStateMachine
            BotLifecycleStateMachine.transition(
                runtime.session,
                BotLifecycleState.RUNNING,
                reason="GAP_RECONCILED: Backlog replayed successfully, restoring RUNNING state",
            )
            logger.info(f"Supervisor restored bot '{bot_id}' from DATA_GAP_BLOCKED to RUNNING.")
        return True
