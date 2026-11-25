"""
libs/bot/orchestration/command_service.py — Internal Bot Application Service (GĐ34)
Provides high-level application control API for managing BotOrchestrator sessions.
Exposes lifecycle commands, status queries, health, and recovery without broker access.
"""

from typing import Dict, Any, List, Optional
import uuid
import logging

from libs.bot.domain import BotSession
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.lifecycle import BotLifecycleState
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.recovery import BotRecoveryManager
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.risk.config import RiskConfig
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.execution.simulation_broker import SimulationBroker

logger = logging.getLogger("bot-command-service")


class BotCommandService:
    """
    Application-level service orchestrating Bot instances and command execution.
    """

    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        recovery_manager: Optional[BotRecoveryManager] = None,
    ):
        self.session_store = session_store or SessionStore()
        self.recovery_manager = recovery_manager or BotRecoveryManager(session_store=self.session_store)
        self._active_orchestrators: Dict[str, BotOrchestrator] = {}

    def create_bot(
        self,
        bot_id: str = "bot_v2_default",
        bot_name: str = "PaperBotV2",
        symbols: Optional[List[str]] = None,
        timeframe: str = "1m",
        initial_cash: float = 100000.0,
        strategy_id: str = "MA_CROSS_1M",
        strategy_version: str = "1.0.0",
        risk_config: Optional[RiskConfig] = None,
        stop_policy: StopPolicy = StopPolicy.CANCEL_REMAINDER,
    ) -> BotOrchestrator:
        """
        Creates and registers a new BotOrchestrator session.
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        r_config = risk_config or RiskConfig()

        session = BotSession(
            session_id=session_id,
            bot_session_id=session_id,
            bot_id=bot_id,
            bot_name=bot_name,
            strategy_name=strategy_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            symbols=symbols or ["NVDA", "BTC/USD"],
            timeframe=timeframe,
            initial_cash=initial_cash,
            risk_config_hash=r_config.compute_hash(),
            status=BotLifecycleState.STOPPED,
            lifecycle_state=BotLifecycleState.STOPPED,
            environment="SIMULATION",
            trading_mode="DRY_RUN",
        )

        portfolio = SimulationPortfolioManager(
            portfolio_id=session_id,
            bot_session_id=session_id,
            initial_cash=initial_cash,
        )
        strategy_engine = StrategyExecutionEngine()
        simulation_broker = SimulationBroker(portfolio=portfolio)

        orchestrator = BotOrchestrator(
            session=session,
            portfolio=portfolio,
            risk_config=r_config,
            strategy_engine=strategy_engine,
            simulation_broker=simulation_broker,
            session_store=self.session_store,
            stop_policy=stop_policy,
        )

        self._active_orchestrators[session_id] = orchestrator
        return orchestrator

    def get_orchestrator(self, session_id: str) -> Optional[BotOrchestrator]:
        """Retrieves active orchestrator instance by session ID."""
        return self._active_orchestrators.get(session_id)

    def start_bot(self, session_id: str) -> bool:
        """Starts a bot session."""
        orch = self.get_orchestrator(session_id)
        if not orch:
            raise ValueError(f"Orchestrator for session {session_id} not found")
        return orch.start()

    def pause_bot(self, session_id: str, reason: str = "OPERATOR_REQUESTED") -> bool:
        """Pauses an active bot session."""
        orch = self.get_orchestrator(session_id)
        if not orch:
            raise ValueError(f"Orchestrator for session {session_id} not found")
        return orch.pause(reason=reason)

    def resume_bot(self, session_id: str) -> bool:
        """Resumes a paused bot session."""
        orch = self.get_orchestrator(session_id)
        if not orch:
            raise ValueError(f"Orchestrator for session {session_id} not found")
        return orch.resume()

    def stop_bot(self, session_id: str, policy: Optional[StopPolicy] = None) -> bool:
        """Gracefully stops a bot session."""
        orch = self.get_orchestrator(session_id)
        if not orch:
            raise ValueError(f"Orchestrator for session {session_id} not found")
        res = orch.stop(policy=policy)
        if res:
            self._active_orchestrators.pop(session_id, None)
        return res

    def get_bot_status(self, session_id: str) -> Dict[str, Any]:
        """Returns the current state and health snapshot."""
        orch = self.get_orchestrator(session_id)
        if orch:
            return {
                "session_id": session_id,
                "lifecycle_state": orch.state,
                "health": orch.get_health(),
                "portfolio_equity": float(orch.portfolio.get_equity()),
                "open_positions": orch.portfolio.positions.get_active_positions_count(),
            }
        session = self.session_store.get_session(session_id)
        if session:
            return {
                "session_id": session_id,
                "lifecycle_state": session.lifecycle_state,
                "status": session.status,
                "error_code": session.error_code,
            }
        return {"session_id": session_id, "status": "NOT_FOUND"}

    def get_performance(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns the performance report for a session."""
        orch = self.get_orchestrator(session_id)
        if orch:
            return orch.get_performance_report()
        # Fallback to persistent report file if available
        rep_path = f"data/paper_bot/performance/perf_{session_id}.json"
        import os, json
        if os.path.exists(rep_path):
            with open(rep_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def trigger_recovery(
        self,
        session_id: str,
        expected_config_hash: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Executes recovery procedure on an existing session."""
        success, err, recovered = self.recovery_manager.recover_session(
            session_id=session_id,
            expected_config_hash=expected_config_hash,
        )
        return success, err
