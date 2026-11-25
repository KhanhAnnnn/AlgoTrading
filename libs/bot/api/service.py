"""
libs/bot/api/service.py — API Application Service Layer (GĐ35)
Bridges FastAPI REST endpoints and WebSockets with BotCommandService and BotOrchestrator.
Dispatches real-time events to BotWebSocketManager upon lifecycle, order, and signal updates.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import asyncio
import uuid
import logging

from libs.bot.domain import (
    BotSession,
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    PortfolioSnapshot,
)
from libs.bot.orchestration.command_service import BotCommandService
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.lifecycle import BotLifecycleState
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.session import SessionStore
from libs.bot.risk.config import RiskConfig
from libs.bot.api.websocket import BotWebSocketManager, ws_manager
from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.telemetry import SupervisorTelemetryCollector

logger = logging.getLogger("v2-bot-service")


class BotApiService:
    """
    Singleton application service providing thread-safe, coordinated access
    to bot orchestrators and real-time event broadcasting.
    """

    def __init__(
        self,
        command_service: Optional[BotCommandService] = None,
        websocket_manager: Optional[BotWebSocketManager] = None,
        supervisor: Optional[MultiBotSupervisor] = None,
    ):
        self.command_service = command_service or BotCommandService()
        self.ws_manager = websocket_manager or ws_manager
        self.supervisor = supervisor or MultiBotSupervisor()

    def _get_active_orchestrator(self, session_id: str) -> Optional[BotOrchestrator]:
        """Finds active orchestrator by session_id or bot_id across command service and supervisor."""
        orch = self.command_service.get_orchestrator(session_id)
        if orch:
            return orch
        # Search supervisor active runtimes
        if hasattr(self, "supervisor") and self.supervisor:
            runtime = self.supervisor.get_bot_runtime(session_id)
            if runtime:
                return runtime.orchestrator
            for r in self.supervisor._active_runtimes.values():
                if r.session.bot_session_id == session_id or r.definition.bot_id == session_id:
                    return r.orchestrator
        # Search by bot_id across command service active orchestrators
        for o in self.command_service._active_orchestrators.values():
            if o.session.bot_id == session_id:
                return o
        return None

    def create_bot(
        self,
        bot_id: str = "bot_v2_default",
        bot_name: str = "PaperBotV2",
        symbols: Optional[List[str]] = None,
        timeframe: str = "1m",
        initial_cash: float = 100000.0,
        strategy_id: str = "MA_CROSS_1M",
        strategy_version: str = "1.0.0",
        risk_config_dict: Optional[Dict[str, Any]] = None,
        stop_policy_str: str = "CANCEL_REMAINDER",
    ) -> Dict[str, Any]:
        """Creates and registers a new BotOrchestrator instance."""
        stop_policy = StopPolicy.CANCEL_REMAINDER if stop_policy_str == "CANCEL_REMAINDER" else StopPolicy.KEEP_WORKING
        r_config = None
        if risk_config_dict:
            r_config = RiskConfig(**risk_config_dict)

        orch = self.command_service.create_bot(
            bot_id=bot_id,
            bot_name=bot_name,
            symbols=symbols or ["NVDA", "BTC/USD"],
            timeframe=timeframe,
            initial_cash=initial_cash,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            risk_config=r_config,
            stop_policy=stop_policy,
        )

        # Register bot definition in supervisor registry if not exists
        if hasattr(self, "supervisor") and self.supervisor:
            if not self.supervisor.registry.get_bot(bot_id):
                try:
                    bot_def = BotDefinition(
                        bot_id=bot_id,
                        bot_name=bot_name,
                        strategy_id=strategy_id,
                        strategy_version=strategy_version,
                        symbols=symbols or ["NVDA", "BTC/USD"],
                        timeframe=timeframe,
                        initial_simulated_cash=initial_cash,
                        risk_config=risk_config_dict or {},
                    )
                    self.supervisor.registry.register_bot(bot_def)
                except Exception as e:
                    logger.debug(f"Could not register in supervisor registry: {e}")

        # Notify via WebSocket if loop is running
        s_id = orch.session.bot_session_id
        self._async_broadcast(
            s_id,
            "BOT_CREATED",
            {"session_id": s_id, "bot_id": bot_id, "status": orch.state},
        )

        return self.get_bot(s_id)

    def list_bots(self) -> List[Dict[str, Any]]:
        """Lists all active and persisted bot sessions."""
        summaries: Dict[str, Dict[str, Any]] = {}

        # 1. Active orchestrators in memory
        for s_id, orch in self.command_service._active_orchestrators.items():
            summaries[s_id] = self._build_bot_summary(orch)

        # 2. Persisted sessions on disk
        persisted = self.command_service.session_store.list_all_sessions()
        for session in persisted:
            if session.bot_session_id not in summaries:
                summaries[session.bot_session_id] = {
                    "session_id": session.bot_session_id,
                    "bot_id": session.bot_id,
                    "bot_name": session.bot_name,
                    "strategy_id": session.strategy_id,
                    "strategy_version": session.strategy_version,
                    "symbols": session.symbols,
                    "timeframe": session.timeframe,
                    "lifecycle_state": session.lifecycle_state,
                    "status": session.status,
                    "initial_cash": session.initial_cash,
                    "current_equity": session.initial_cash,
                    "cash": session.initial_cash,
                    "available_cash": session.initial_cash,
                    "reserved_cash": 0.0,
                    "market_value": 0.0,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                    "open_positions_count": 0,
                    "started_at": session.started_at.isoformat() if session.started_at else None,
                    "paused_at": session.paused_at.isoformat() if session.paused_at else None,
                    "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
                    "last_heartbeat_at": session.last_heartbeat_at.isoformat() if session.last_heartbeat_at else None,
                    "error_code": session.error_code,
                    "error_message": session.error_message,
                    "risk_config_hash": session.risk_config_hash,
                    "trading_mode": session.trading_mode,
                    "environment": session.environment,
                }

        return list(summaries.values())

    def get_bot(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves aggregated summary for a single bot session."""
        orch = self._get_active_orchestrator(session_id)
        if orch:
            return self._build_bot_summary(orch)

        # Check persisted session
        session = self.command_service.session_store.get_session(session_id)
        if session:
            return {
                "session_id": session.bot_session_id,
                "bot_id": session.bot_id,
                "bot_name": session.bot_name,
                "strategy_id": session.strategy_id,
                "strategy_version": session.strategy_version,
                "symbols": session.symbols,
                "timeframe": session.timeframe,
                "lifecycle_state": session.lifecycle_state,
                "status": session.status,
                "initial_cash": session.initial_cash,
                "current_equity": session.initial_cash,
                "cash": session.initial_cash,
                "available_cash": session.initial_cash,
                "reserved_cash": 0.0,
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "open_positions_count": 0,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "paused_at": session.paused_at.isoformat() if session.paused_at else None,
                "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
                "last_heartbeat_at": session.last_heartbeat_at.isoformat() if session.last_heartbeat_at else None,
                "error_code": session.error_code,
                "error_message": session.error_message,
                "risk_config_hash": session.risk_config_hash,
                "trading_mode": session.trading_mode,
                "environment": session.environment,
            }
        return None

    def start_bot(self, session_id: str) -> Dict[str, Any]:
        """Starts the bot session. Idempotent if already RUNNING."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            session = self.command_service.session_store.get_session(session_id)
            if session:
                raise ValueError(f"Cannot start bot in state '{session.lifecycle_state}'")
            raise KeyError(f"Bot session '{session_id}' not found")

        if orch.state == BotLifecycleState.RUNNING:
            return self.get_bot(orch.session.bot_session_id)

        if orch.state == BotLifecycleState.ERROR:
            raise ValueError(f"Cannot start bot in ERROR state: {orch.session.error_code}")

        res = orch.start()
        if not res:
            raise RuntimeError(f"Failed to start bot '{session_id}': {orch.session.error_message}")

        self._async_broadcast(
            orch.session.bot_session_id,
            "BOT_LIFECYCLE_EVENT",
            {"action": "START", "state": orch.state, "session_id": orch.session.bot_session_id},
        )
        return self.get_bot(orch.session.bot_session_id)

    def pause_bot(self, session_id: str, reason: str = "API_REQUEST") -> Dict[str, Any]:
        """Pauses the bot session. Idempotent if already PAUSED."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            session = self.command_service.session_store.get_session(session_id)
            if session:
                raise ValueError(f"Cannot pause bot in state '{session.lifecycle_state}'")
            raise KeyError(f"Bot session '{session_id}' not found")

        if orch.state == BotLifecycleState.PAUSED:
            return self.get_bot(orch.session.bot_session_id)

        if orch.state != BotLifecycleState.RUNNING:
            raise ValueError(f"Cannot pause bot in state '{orch.state}'")

        res = orch.pause(reason=reason)
        if not res:
            raise RuntimeError(f"Failed to pause bot '{session_id}'")

        self._async_broadcast(
            orch.session.bot_session_id,
            "BOT_LIFECYCLE_EVENT",
            {"action": "PAUSE", "state": orch.state, "reason": reason, "session_id": orch.session.bot_session_id},
        )
        return self.get_bot(orch.session.bot_session_id)

    def resume_bot(self, session_id: str) -> Dict[str, Any]:
        """Resumes the bot session. Idempotent if already RUNNING."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            session = self.command_service.session_store.get_session(session_id)
            if session:
                raise ValueError(f"Cannot resume bot in state '{session.lifecycle_state}'. Bot must be PAUSED.")
            raise KeyError(f"Bot session '{session_id}' not found")

        if orch.state == BotLifecycleState.RUNNING:
            return self.get_bot(orch.session.bot_session_id)

        if orch.state != BotLifecycleState.PAUSED:
            raise ValueError(f"Cannot resume bot in state '{orch.state}'. Bot must be PAUSED.")

        res = orch.resume()
        if not res:
            raise RuntimeError(f"Failed to resume bot '{session_id}'")

        self._async_broadcast(
            orch.session.bot_session_id,
            "BOT_LIFECYCLE_EVENT",
            {"action": "RESUME", "state": orch.state, "session_id": orch.session.bot_session_id},
        )
        return self.get_bot(orch.session.bot_session_id)

    def stop_bot(self, session_id: str, policy_str: Optional[str] = None) -> Dict[str, Any]:
        """Stops the bot session with specified StopPolicy. Idempotent if already STOPPED."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            # Check if it was already stopped on disk
            session = self.command_service.session_store.get_session(session_id)
            if session and session.lifecycle_state == BotLifecycleState.STOPPED:
                return self.get_bot(session_id)
            raise KeyError(f"Bot session '{session_id}' not found")

        if orch.state == BotLifecycleState.STOPPED:
            return self.get_bot(orch.session.bot_session_id)

        policy = None
        if policy_str:
            policy = StopPolicy.CANCEL_REMAINDER if policy_str == "CANCEL_REMAINDER" else StopPolicy.KEEP_WORKING

        s_id = orch.session.bot_session_id
        res = orch.stop(policy=policy)
        if not res:
            raise RuntimeError(f"Failed to stop bot '{session_id}'")

        # Keep stopped orchestrator in active map for post-mortem telemetry/queries
        self.command_service._active_orchestrators[s_id] = orch

        self._async_broadcast(
            s_id,
            "BOT_LIFECYCLE_EVENT",
            {"action": "STOP", "state": "STOPPED", "session_id": s_id},
        )
        return self.get_bot(s_id)

    def get_portfolio(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns detailed portfolio snapshot and position table."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            bot = self.get_bot(session_id)
            if not bot:
                return None
            initial_c = float(getattr(bot, "initial_cash", 100000.0))
            return {
                "session_id": getattr(bot, "session_id", session_id),
                "portfolio_id": f"port_{session_id}",
                "state": getattr(bot, "lifecycle_state", "STOPPED"),
                "initial_cash": initial_c,
                "cash": float(getattr(bot, "cash", initial_c) or initial_c),
                "available_cash": float(getattr(bot, "available_cash", initial_c) or initial_c),
                "reserved_cash": float(getattr(bot, "reserved_cash", 0.0) or 0.0),
                "equity": float(getattr(bot, "current_equity", initial_c) or initial_c),
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": float(getattr(bot, "realized_pnl", 0.0) or 0.0),
                "positions": [],
                "environment": "SIMULATION",
            }

        p = orch.portfolio
        positions = []
        for sym, pos in p.positions.get_all_positions().items():
            positions.append({
                "symbol": sym,
                "qty": pos.qty,
                "avg_entry_price": pos.avg_entry_price,
                "current_price": pos.current_price,
                "cost_basis": pos.cost_basis,
                "market_value": pos.market_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "realized_pnl": pos.realized_pnl,
                "environment": pos.environment,
            })

        return {
            "session_id": orch.session.bot_session_id,
            "portfolio_id": p.portfolio_id,
            "state": p.state,
            "initial_cash": float(orch.session.initial_cash),
            "cash": float(p.cash),
            "available_cash": float(p.available_cash),
            "reserved_cash": float(p.reserved_cash),
            "equity": float(p.get_equity()),
            "market_value": float(p.positions.get_total_market_value()),
            "unrealized_pnl": float(p.positions.get_total_unrealized_pnl()),
            "realized_pnl": float(p.realized_pnl),
            "positions": positions,
            "environment": "SIMULATION",
        }

    def get_orders(
        self,
        session_id: str,
        status_filter: Optional[str] = None,
        symbol_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves simulated orders from active broker or persisted order store."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            return []

        orders: List[SimulatedOrder] = list(orch.simulation_broker.order_manager._orders.values())
        if status_filter:
            orders = [o for o in orders if o.status == status_filter.upper()]
        if symbol_filter:
            orders = [o for o in orders if o.symbol.upper() == symbol_filter.upper()]

        return [
            {
                "simulated_order_id": o.simulated_order_id,
                "bot_session_id": o.bot_session_id,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "quantity": o.quantity,
                "filled_quantity": o.filled_quantity,
                "remaining_quantity": o.remaining_quantity,
                "average_fill_price": o.average_fill_price,
                "status": o.status,
                "limit_price": o.limit_price,
                "stop_price": o.stop_price,
                "submitted_at": getattr(o, "submitted_at", None).isoformat() if getattr(o, "submitted_at", None) else None,
                "filled_at": getattr(o, "filled_at", None).isoformat() if getattr(o, "filled_at", None) else None,
                "cancelled_at": getattr(o, "cancelled_at", None).isoformat() if getattr(o, "cancelled_at", None) else None,
                "rejection_reason": o.rejection_reason,
                "environment": o.environment,
            }
            for o in orders
        ]

    def get_fills(
        self,
        session_id: str,
        symbol_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieves simulated fills."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            return []

        fills: List[SimulatedFill] = orch.simulation_broker._fills
        if symbol_filter:
            fills = [f for f in fills if f.symbol.upper() == symbol_filter.upper()]

        fills = fills[-limit:]
        return [
            {
                "simulated_fill_id": f.simulated_fill_id,
                "simulated_order_id": f.simulated_order_id,
                "symbol": f.symbol,
                "side": f.side,
                "fill_price": f.fill_price,
                "fill_qty": f.fill_qty,
                "fee": f.fee,
                "slippage": f.slippage,
                "fill_time": f.fill_time.isoformat() if isinstance(f.fill_time, datetime) else str(f.fill_time),
                "source_bar_key": f.source_bar_key,
                "execution_bar_key": f.execution_bar_key,
                "environment": f.environment,
            }
            for f in fills
        ]

    def get_performance(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Compiles and returns real-time performance report."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            bot = self.get_bot(session_id)
            if not bot:
                return None
            initial_c = float(getattr(bot, "initial_cash", 100000.0))
            now_iso = datetime.now(timezone.utc).isoformat()
            return {
                "session_id": getattr(bot, "session_id", session_id),
                "report_generated_at": now_iso,
                "capital_metrics": {"initial_cash": initial_c, "equity": initial_c},
                "pnl_metrics": {"realized_pnl": 0.0, "unrealized_pnl": 0.0},
                "drawdown_metrics": {"current_drawdown_pct": 0.0, "peak_equity": initial_c},
                "signal_metrics": {"signals_received": 0, "signals_accepted": 0, "signals_rejected": 0},
                "order_metrics": {"orders_submitted": 0, "orders_filled": 0},
                "financial": {},
                "signals": {},
                "orders": {},
                "trades": {"win_rate_pct": 0.0, "total_trades": 0},
                "total_realized_pnl": 0.0,
                "win_rate_pct": 0.0,
                "total_trades": 0,
                "signals_received": 0,
                "signals_accepted": 0,
                "signals_rejected": 0,
                "max_drawdown_usd": 0.0,
                "max_drawdown_pct": 0.0,
                "peak_equity": initial_c,
                "environment": "SIMULATION",
            }

        report = orch.get_performance_report()
        report["environment"] = "SIMULATION"
        pnl = report.get("pnl_metrics", {})
        dd = report.get("drawdown_metrics", {})
        sig = report.get("signal_metrics", {})
        tr = report.get("trades", {})
        report["total_realized_pnl"] = float(pnl.get("realized_pnl", 0.0))
        report["win_rate_pct"] = float(tr.get("win_rate_pct", 0.0))
        report["total_trades"] = int(tr.get("total_trades", 0))
        report["signals_received"] = int(sig.get("signals_received", 0))
        report["signals_accepted"] = int(sig.get("signals_accepted", 0))
        report["signals_rejected"] = int(sig.get("signals_rejected", 0))
        report["max_drawdown_usd"] = float(dd.get("drawdown_amount", 0.0))
        report["max_drawdown_pct"] = float(dd.get("current_drawdown_pct", 0.0))
        report["peak_equity"] = float(dd.get("peak_equity", 0.0))
        return report

    def get_health(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns health monitor status."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            bot = self.get_bot(session_id)
            if not bot:
                return None
            return {
                "session_id": getattr(bot, "session_id", session_id),
                "lifecycle_state": getattr(bot, "lifecycle_state", "STOPPED"),
                "overall_status": "HEALTHY",
                "status": getattr(bot, "status", "STOPPED"),
                "last_heartbeat_age_seconds": 0.0,
                "events_processed_count": 0,
                "event_processing_latency_ms": 0.0,
                "latency_ms": 0.0,
                "queue_depth": 0,
                "consumer_health": "HEALTHY",
                "strategy_engine_health": "HEALTHY",
                "simulation_broker_health": "HEALTHY",
                "reconciliation_status": "BALANCED",
                "is_feed_stale": False,
                "warnings": [],
                "error_count": 0,
                "last_error": None,
                "environment": "SIMULATION",
            }
        health = orch.get_health()
        health["environment"] = "SIMULATION"
        health["event_processing_latency_ms"] = float(health.get("processing_latency_ms", 0.0))
        health["latency_ms"] = float(health.get("processing_latency_ms", 0.0))
        health["status"] = health.get("overall_status", "HEALTHY")
        health["is_feed_stale"] = float(health.get("last_heartbeat_age_seconds", 0.0)) > 300.0
        health["warnings"] = []
        if health.get("last_error"):
            health["warnings"].append({"code": "LAST_ERROR", "message": health["last_error"]})
        return health

    def submit_bar(self, session_id: str, bar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submits an incoming 1m market data event to the bot event loop."""
        orch = self._get_active_orchestrator(session_id)
        if not orch:
            raise KeyError(f"Bot session '{session_id}' not found")

        ev_time = bar_data.get("event_time")
        if isinstance(ev_time, str):
            ev_time = datetime.fromisoformat(ev_time)
        elif not isinstance(ev_time, datetime):
            ev_time = datetime.now(timezone.utc)

        bar = MarketDataEvent(
            event_id=f"evt_{bar_data['symbol']}_{uuid.uuid4().hex[:8]}",
            symbol=bar_data["symbol"],
            timeframe=bar_data.get("timeframe", "1m"),
            event_time=ev_time,
            open=float(bar_data["open"]),
            high=float(bar_data["high"]),
            low=float(bar_data["low"]),
            close=float(bar_data["close"]),
            volume=float(bar_data["volume"]),
            is_final=bar_data.get("is_final", True),
            environment=bar_data.get("environment", "SIMULATION"),
        )

        res = orch.submit_bar(bar, auto_process=True)
        if not res:
            return {"status": "REJECTED_OR_PAUSED", "state": orch.state}

        # Broadcast events
        s_id = orch.session.bot_session_id
        if res.get("signal"):
            sig = res["signal"]
            self._async_broadcast(s_id, "STRATEGY_SIGNAL_EVENT", {
                "signal_id": sig.signal_id,
                "strategy_id": sig.strategy_id,
                "symbol": sig.symbol,
                "signal_type": sig.signal_type,
                "price": sig.price,
                "strength": sig.strength,
            })

        if res.get("decision"):
            dec = res["decision"]
            self._async_broadcast(s_id, "RISK_DECISION_EVENT", {
                "decision_id": dec.decision_id,
                "status": dec.status,
                "rejection_reason": dec.rejection_reason,
                "reason_codes": dec.reason_codes,
            })

        if res.get("fills_generated", 0) > 0:
            self._async_broadcast(s_id, "FILL_EVENT", {
                "fills_count": res["fills_generated"],
                "bar_key": bar.bar_key,
            })
            # Also broadcast portfolio update
            snap = self.get_portfolio(s_id)
            if snap:
                self._async_broadcast(s_id, "PORTFOLIO_UPDATE", snap)

        return res

    def get_snapshot(self, session_id: str) -> Dict[str, Any]:
        """Compiles a complete real-time state snapshot for WebSocket initialization."""
        summary = self.get_bot(session_id)
        portfolio = self.get_portfolio(session_id)
        orders = self.get_orders(session_id)
        fills = self.get_fills(session_id, limit=20)
        health = self.get_health(session_id)
        performance = self.get_performance(session_id)

        return {
            "summary": summary,
            "portfolio": portfolio,
            "orders": orders,
            "fills": fills,
            "health": health,
            "performance": performance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": "SIMULATION",
        }

    def _build_bot_summary(self, orch: BotOrchestrator) -> Dict[str, Any]:
        """Builds summary dictionary for an active orchestrator."""
        session = orch.session
        p = orch.portfolio
        equity = float(p.get_equity())
        cash = float(p.cash)
        avail = float(p.available_cash)
        reserved = float(p.reserved_cash)
        market_val = float(p.positions.get_total_market_value())
        unrealized = float(p.positions.get_total_unrealized_pnl())
        realized = float(p.realized_pnl)
        open_count = p.positions.get_active_positions_count()

        return {
            "session_id": session.bot_session_id,
            "bot_id": session.bot_id,
            "bot_name": session.bot_name,
            "strategy_id": session.strategy_id,
            "strategy_version": session.strategy_version,
            "symbols": session.symbols,
            "timeframe": session.timeframe,
            "lifecycle_state": orch.state,
            "status": session.status,
            "initial_cash": session.initial_cash,
            "current_equity": equity,
            "cash": cash,
            "available_cash": avail,
            "reserved_cash": reserved,
            "market_value": market_val,
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
            "open_positions_count": open_count,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "paused_at": session.paused_at.isoformat() if session.paused_at else None,
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
            "last_heartbeat_at": session.last_heartbeat_at.isoformat() if session.last_heartbeat_at else None,
            "error_code": session.error_code,
            "error_message": session.error_message,
            "risk_config_hash": session.risk_config_hash,
            "trading_mode": session.trading_mode,
            "environment": session.environment,
        }

    def _async_broadcast(self, session_id: str, event_type: str, payload: Dict[str, Any]):
        """Dispatches event to WebSocket manager in running event loop or schedule task."""
        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = getattr(self.ws_manager, "_main_loop", None)

            if loop and loop.is_running():
                # If we are in the same loop thread
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop is loop:
                        loop.create_task(self.ws_manager.broadcast_event(session_id, event_type, payload))
                        return
                except RuntimeError:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_manager.broadcast_event(session_id, event_type, payload),
                    loop
                )
        except Exception as e:
            logger.debug(f"Broadcast event ignored: {e}")

    def get_supervisor_overview(self) -> Dict[str, Any]:
        """Returns aggregated telemetry, bot states, and health from supervisor."""
        if hasattr(self, "supervisor") and self.supervisor:
            return SupervisorTelemetryCollector.collect_telemetry(self.supervisor)
        return {
            "status": "HEALTHY",
            "active_bots_count": len(self.command_service._active_orchestrators),
            "disclaimer": SupervisorTelemetryCollector.CAPITAL_DISCLAIMER,
            "environment": "SIMULATION",
            "trading_mode": "DRY_RUN",
        }

    def list_bot_sessions(self, bot_id: str) -> List[Dict[str, Any]]:
        """Queries all past and current sessions for a given bot_id."""
        if hasattr(self, "supervisor") and self.supervisor:
            sessions = self.supervisor.registry.list_sessions_for_bot(bot_id, self.command_service.session_store)
        else:
            sessions = [s for s in self.command_service.session_store.list_all_sessions() if s.bot_id == bot_id]
        
        return [
            {
                "session_id": s.bot_session_id,
                "bot_id": s.bot_id,
                "bot_name": s.bot_name,
                "strategy_id": s.strategy_id,
                "symbols": s.symbols,
                "lifecycle_state": s.lifecycle_state,
                "status": s.status,
                "initial_cash": s.initial_cash,
                "created_at": s.created_at.isoformat() if isinstance(s.created_at, datetime) else str(s.created_at),
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "stopped_at": s.stopped_at.isoformat() if s.stopped_at else None,
                "checkpoint_id": s.checkpoint_id,
            }
            for s in sessions
        ]

    def archive_bot(self, bot_id: str) -> bool:
        """Soft-archives a bot definition in the registry."""
        if hasattr(self, "supervisor") and self.supervisor:
            return self.supervisor.registry.archive_bot(bot_id)
        return False

    def dispatch_bar(self, bar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fans out incoming market data event to all subscribed bots via supervisor."""
        ev_time = bar_data.get("event_time")
        if isinstance(ev_time, str):
            ev_time = datetime.fromisoformat(ev_time)
        elif not isinstance(ev_time, datetime):
            ev_time = datetime.now(timezone.utc)

        bar = MarketDataEvent(
            event_id=f"evt_{bar_data['symbol']}_{uuid.uuid4().hex[:8]}",
            symbol=bar_data["symbol"],
            timeframe=bar_data.get("timeframe", "1m"),
            event_time=ev_time,
            open=float(bar_data["open"]),
            high=float(bar_data["high"]),
            low=float(bar_data["low"]),
            close=float(bar_data["close"]),
            volume=float(bar_data["volume"]),
            is_final=bar_data.get("is_final", True),
            environment=bar_data.get("environment", "SIMULATION"),
        )

        if hasattr(self, "supervisor") and self.supervisor:
            return self.supervisor.dispatch_market_data(bar, auto_process=True)
        return {"status": "DISPATCHER_UNAVAILABLE"}


# Global singleton instance
bot_api_service = BotApiService()
