"""
libs/bot/multibot/telemetry.py — Multi-Bot Aggregated Telemetry Collector (GĐ37)
Aggregates health, volume, and virtual equity metrics across concurrent bots.
Enforces explicit disclaimer that simulation portfolios are independent and non-fungible.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.orchestration.lifecycle import BotLifecycleState

logger = logging.getLogger("multibot-telemetry")


class SupervisorTelemetryCollector:
    """
    Collects and compiles aggregated telemetry, metrics, and health for MultiBotSupervisor.
    """

    CAPITAL_DISCLAIMER = (
        "INDEPENDENT_VIRTUAL_SIMULATION_CAPITAL_ONLY — Portfolios are strictly isolated, "
        "virtual, non-fungible, and must not be blended or represented as a single trading account."
    )

    @classmethod
    def collect_telemetry(cls, supervisor: MultiBotSupervisor) -> Dict[str, Any]:
        """
        Gathers system-wide metrics across all active and registered bots.
        """
        registered_bots = supervisor.registry.list_bots(include_archived=False)
        active_runtimes = supervisor._active_runtimes

        active_count = 0
        paused_count = 0
        stopped_count = 0
        error_count = 0

        total_simulated_cash = 0.0
        total_simulated_equity = 0.0
        total_unrealized_pnl = 0.0
        total_realized_pnl = 0.0
        total_open_orders = 0
        total_fills = 0

        bot_summaries = []

        for b_id, runtime in active_runtimes.items():
            state = runtime.state
            if state == BotLifecycleState.RUNNING:
                active_count += 1
            elif state == BotLifecycleState.PAUSED:
                paused_count += 1
            elif state == BotLifecycleState.ERROR:
                error_count += 1
            elif state == BotLifecycleState.STOPPED:
                stopped_count += 1

            snap = runtime.orchestrator.portfolio.get_portfolio_snapshot()
            total_simulated_cash += float(snap.cash)
            total_simulated_equity += float(snap.equity)
            total_unrealized_pnl += float(snap.unrealized_pnl)
            total_realized_pnl += float(snap.realized_pnl)

            open_orders = runtime.orchestrator.simulation_broker.order_manager.get_open_orders()
            total_open_orders += len(open_orders)
            total_fills += len(runtime.orchestrator.simulation_broker._fills)

            bot_summaries.append({
                "bot_id": b_id,
                "session_id": runtime.session_id,
                "bot_name": runtime.definition.bot_name,
                "strategy_id": runtime.definition.strategy_id,
                "symbols": runtime.definition.symbols,
                "state": state,
                "cash": float(snap.cash),
                "equity": float(snap.equity),
                "open_orders": len(open_orders),
                "fills": len(runtime.orchestrator.simulation_broker._fills),
            })

        dispatcher_telemetry = supervisor.dispatcher.get_telemetry()
        health = supervisor.get_supervisor_health()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_registered_bots": len(registered_bots),
            "active_bots_count": len(active_runtimes),
            "bot_counts_by_state": {
                "RUNNING": active_count,
                "PAUSED": paused_count,
                "STOPPED": stopped_count,
                "ERROR": error_count,
            },
            "aggregate_simulation_capital": {
                "total_simulated_cash": round(total_simulated_cash, 2),
                "total_simulated_equity": round(total_simulated_equity, 2),
                "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                "total_realized_pnl": round(total_realized_pnl, 2),
                "disclaimer": cls.CAPITAL_DISCLAIMER,
            },
            "aggregate_orders": {
                "total_open_orders": total_open_orders,
                "total_fills": total_fills,
            },
            "dispatcher": dispatcher_telemetry,
            "system_health": health,
            "bots": bot_summaries,
            "environment": "SIMULATION",
            "trading_mode": "DRY_RUN",
            "paper_execution_gate": "CLOSED",
        }
