"""
libs/bot/multibot/isolation.py — Multi-Bot State, Resource & Storage Isolation (GĐ37)
Guarantees complete sandbox isolation: independent portfolios, position books, cash,
orders, fills, ledgers, journals, and checkpoints per bot session.
"""

from typing import Dict, Any, Optional
import os
import uuid
import logging

from libs.bot.domain import BotSession
from libs.bot.multibot.registry import BotDefinition
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.bot.execution.order_store import OrderStore
from libs.bot.execution.fill_store import FillStore
from libs.bot.execution.ledger import ExecutionLedger
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.checkpoint import BotCheckpointManager
from libs.bot.orchestration.event_journal import BotEventJournal
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.lifecycle import BotLifecycleState

logger = logging.getLogger("multibot-isolation")


def get_bot_storage_dir(bot_id: str, session_id: str, base_dir: str = "data/paper_bot") -> str:
    """Returns the dedicated path-isolated directory for a specific bot session."""
    return os.path.join(base_dir, "bots", bot_id, "sessions", session_id)


def get_bot_order_store_dir(bot_id: str, session_id: str, base_dir: str = "data/paper_bot") -> str:
    """Returns the dedicated order store path for a bot session."""
    return os.path.join(get_bot_storage_dir(bot_id, session_id, base_dir), "orders")


def get_bot_fill_store_dir(bot_id: str, session_id: str, base_dir: str = "data/paper_bot") -> str:
    """Returns the dedicated fill store path for a bot session."""
    return os.path.join(get_bot_storage_dir(bot_id, session_id, base_dir), "fills")


def get_bot_checkpoint_dir(bot_id: str, session_id: str, base_dir: str = "data/paper_bot") -> str:
    """Returns the dedicated checkpoints directory for a bot session."""
    return os.path.join(get_bot_storage_dir(bot_id, session_id, base_dir), "checkpoints")


def get_bot_journal_dir(bot_id: str, session_id: str, base_dir: str = "data/paper_bot") -> str:
    """Returns the dedicated event journal directory for a bot session."""
    return os.path.join(get_bot_storage_dir(bot_id, session_id, base_dir), "journal")


class BotSandboxFactory:
    """
    Factory creating fully isolated runtime sandboxes for simulation bots.
    Ensures that concurrent bots (even trading identical symbols) maintain strictly
    decoupled position books, cash balances, order books, and audit trails.
    """

    @staticmethod
    def create_sandbox(
        definition: BotDefinition,
        session_id: Optional[str] = None,
        base_dir: str = "data/paper_bot",
        stop_policy: StopPolicy = StopPolicy.CANCEL_REMAINDER,
        max_queue_size: int = 1000,
    ) -> Dict[str, Any]:
        """
        Builds and wires all isolated components for a bot session.
        Returns a dictionary containing orchestrator, session, portfolio, broker, and stores.
        """
        sess_id = session_id or f"sess_{definition.bot_id}_{uuid.uuid4().hex[:8]}"

        # Create isolated directory paths
        sess_dir = get_bot_storage_dir(definition.bot_id, sess_id, base_dir)
        orders_dir = get_bot_order_store_dir(definition.bot_id, sess_id, base_dir)
        fills_dir = get_bot_fill_store_dir(definition.bot_id, sess_id, base_dir)
        checkpoints_dir = get_bot_checkpoint_dir(definition.bot_id, sess_id, base_dir)
        journal_dir = get_bot_journal_dir(definition.bot_id, sess_id, base_dir)
        sessions_dir = os.path.join(base_dir, "sessions")

        for d in [sess_dir, orders_dir, fills_dir, checkpoints_dir, journal_dir, sessions_dir]:
            os.makedirs(d, exist_ok=True)

        # 1. Isolated Risk Config
        risk_dict = dict(definition.risk_config)
        risk_config = RiskConfig(**risk_dict) if risk_dict else RiskConfig()

        # 2. Isolated Bot Session
        session = BotSession(
            session_id=sess_id,
            bot_session_id=sess_id,
            bot_id=definition.bot_id,
            bot_name=definition.bot_name,
            strategy_name=definition.strategy_id,
            strategy_id=definition.strategy_id,
            strategy_version=definition.strategy_version,
            symbols=list(definition.symbols),
            timeframe=definition.timeframe,
            initial_cash=float(definition.initial_simulated_cash),
            risk_config_hash=risk_config.compute_hash(),
            status=BotLifecycleState.STOPPED,
            lifecycle_state=BotLifecycleState.STOPPED,
            environment="SIMULATION",
            trading_mode="DRY_RUN",
        )

        # 3. Isolated Stores & Ledgers
        order_store = OrderStore(storage_dir=orders_dir)
        fill_store = FillStore(storage_dir=fills_dir)
        ledger = ExecutionLedger(storage_dir=sess_dir)
        checkpoint_manager = BotCheckpointManager(storage_dir=checkpoints_dir)
        session_store = SessionStore(storage_dir=sessions_dir)
        journal = BotEventJournal(sess_id, storage_dir=journal_dir)

        # 4. Isolated Portfolio Manager
        port_id = f"port_{definition.bot_id}_{sess_id}"
        portfolio = SimulationPortfolioManager(
            portfolio_id=port_id,
            bot_session_id=sess_id,
            initial_cash=float(definition.initial_simulated_cash),
        )

        # 5. Isolated Simulation Broker
        simulation_broker = SimulationBroker(
            portfolio=portfolio,
            order_store=order_store,
            fill_store=fill_store,
            ledger=ledger,
        )

        # 6. Isolated Strategy Execution Engine
        strategy_engine = StrategyExecutionEngine()
        strat_cfg = dict(definition.execution_config.get("strategy_config", {}))
        if definition.strategy_id == "MA_CROSS_1M":
            strat_cfg.setdefault("fast_period", 5)
            strat_cfg.setdefault("slow_period", 20)
        elif definition.strategy_id == "RSI_1M":
            strat_cfg.setdefault("period", 14)
            strat_cfg.setdefault("oversold", 30.0)
            strat_cfg.setdefault("overbought", 70.0)
        strategy_engine.attach_strategy(
            strategy_id=definition.strategy_id,
            symbols=definition.symbols,
            configuration=strat_cfg,
        )

        # 7. Isolated Orchestrator
        orchestrator = BotOrchestrator(
            session=session,
            portfolio=portfolio,
            risk_config=risk_config,
            strategy_engine=strategy_engine,
            simulation_broker=simulation_broker,
            session_store=session_store,
            checkpoint_manager=checkpoint_manager,
            journal=journal,
            stop_policy=stop_policy,
            max_queue_size=max_queue_size,
        )

        logger.info(
            f"Created isolated sandbox for bot '{definition.bot_id}', session '{sess_id}' "
            f"at '{sess_dir}'"
        )

        return {
            "session_id": sess_id,
            "session": session,
            "orchestrator": orchestrator,
            "portfolio": portfolio,
            "simulation_broker": simulation_broker,
            "strategy_engine": strategy_engine,
            "order_store": order_store,
            "fill_store": fill_store,
            "ledger": ledger,
            "checkpoint_manager": checkpoint_manager,
            "session_store": session_store,
        }
