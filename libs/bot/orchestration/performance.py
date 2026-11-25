"""
libs/bot/orchestration/performance.py — Session Performance Reporting (GĐ34)
Calculates and persists quantitative performance metrics for a simulation bot session.
Storage directory: data/paper_bot/performance/
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import json
import os
from datetime import datetime, timezone

from libs.bot.domain import BotSession, SimulatedOrder, SimulatedFill
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal, quantize_currency


class BotPerformanceReporter:
    """
    Aggregates financial, signal, order, and execution metrics into reproducible performance reports.
    """

    def __init__(self, session_id: str, storage_dir: str = "data/paper_bot/performance"):
        self.session_id = session_id
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def generate_report(
        self,
        session: BotSession,
        portfolio: SimulationPortfolioManager,
        orders: List[SimulatedOrder],
        fills: List[SimulatedFill],
        signals_received: int = 0,
        signals_accepted: int = 0,
        signals_rejected: int = 0,
    ) -> Dict[str, Any]:
        """
        Compiles exhaustive performance metrics from current session state.
        """
        snapshot = portfolio.get_portfolio_snapshot()
        init_eq = to_decimal(session.initial_cash)
        curr_eq = to_decimal(portfolio.get_equity())
        cash = to_decimal(portfolio.cash)
        avail_cash = to_decimal(portfolio.available_cash)
        res_cash = to_decimal(portfolio.reserved_cash)

        realized_pnl = to_decimal(portfolio.realized_pnl)
        unrealized_pnl = to_decimal(portfolio.positions.get_total_unrealized_pnl())
        market_val = to_decimal(portfolio.positions.get_total_market_value())

        # Calculate fees and slippage from fills
        total_fees = Decimal("0.0")
        total_slippage = Decimal("0.0")
        total_filled_qty = Decimal("0.0")
        turnover = Decimal("0.0")

        for f in fills:
            q = to_decimal(f.fill_qty)
            p = to_decimal(f.fill_price)
            fee = to_decimal(f.fee)
            slip = to_decimal(f.slippage) * q
            total_fees += fee
            total_slippage += slip
            total_filled_qty += q
            turnover += (q * p)

        gross_pnl = realized_pnl + unrealized_pnl
        net_pnl = gross_pnl - total_fees
        return_pct = ((curr_eq - init_eq) / init_eq * Decimal("100.0")) if init_eq > Decimal("0") else Decimal("0.0")

        peak_eq = to_decimal(portfolio.peak_equity)
        dd_amt = max(Decimal("0.0"), peak_eq - curr_eq)
        curr_dd_pct = (dd_amt / peak_eq * Decimal("100.0")) if peak_eq > Decimal("0") else Decimal("0.0")

        # Order statistics
        filled_orders = len([o for o in orders if o.status == "FILLED"])
        partially_filled_orders = len([o for o in orders if o.status == "PARTIALLY_FILLED"])
        cancelled_orders = len([o for o in orders if o.status == "CANCELLED"])
        expired_orders = len([o for o in orders if o.status == "EXPIRED"])
        total_orders = len(orders)
        fill_rate = (filled_orders / total_orders * 100.0) if total_orders > 0 else 0.0

        # Position snapshot
        open_positions = {
            sym: {
                "qty": p.qty,
                "avg_price": p.avg_entry_price,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
            }
            for sym, p in portfolio.positions.get_all_positions().items()
            if abs(p.qty) > 1e-9
        }

        report = {
            "session_id": session.bot_session_id,
            "bot_name": session.bot_name,
            "strategy_id": session.strategy_id,
            "strategy_version": session.strategy_version,
            "timeframe": session.timeframe,
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "capital_metrics": {
                "initial_equity": float(quantize_currency(init_eq)),
                "current_equity": float(quantize_currency(curr_eq)),
                "cash": float(quantize_currency(cash)),
                "available_cash": float(quantize_currency(avail_cash)),
                "reserved_cash": float(quantize_currency(res_cash)),
                "market_value": float(quantize_currency(market_val)),
            },
            "pnl_metrics": {
                "realized_pnl": float(quantize_currency(realized_pnl)),
                "unrealized_pnl": float(quantize_currency(unrealized_pnl)),
                "gross_pnl": float(quantize_currency(gross_pnl)),
                "total_fees": float(quantize_currency(total_fees)),
                "estimated_slippage": float(quantize_currency(total_slippage)),
                "net_pnl": float(quantize_currency(net_pnl)),
                "return_pct": float(round(return_pct, 4)),
            },
            "drawdown_metrics": {
                "peak_equity": float(quantize_currency(peak_eq)),
                "drawdown_amount": float(quantize_currency(dd_amt)),
                "current_drawdown_pct": float(round(curr_dd_pct, 4)),
            },
            "signal_metrics": {
                "signals_received": signals_received,
                "signals_accepted": signals_accepted,
                "signals_rejected": signals_rejected,
            },
            "order_metrics": {
                "total_orders": total_orders,
                "filled_orders": filled_orders,
                "partially_filled_orders": partially_filled_orders,
                "cancelled_orders": cancelled_orders,
                "expired_orders": expired_orders,
                "fill_rate_pct": round(fill_rate, 2),
                "total_filled_quantity": float(total_filled_qty),
                "turnover": float(quantize_currency(turnover)),
            },
            "open_positions": open_positions,
            "financial": {
                "initial_equity": float(quantize_currency(init_eq)),
                "current_equity": float(quantize_currency(curr_eq)),
                "total_return_pct": float(round(return_pct, 4)),
                "realized_pnl": float(quantize_currency(realized_pnl)),
                "unrealized_pnl": float(quantize_currency(unrealized_pnl)),
            },
            "signals": {
                "signals_received": signals_received,
                "signals_accepted": signals_accepted,
                "signals_rejected": signals_rejected,
                "acceptance_rate_pct": round((signals_accepted / signals_received * 100.0), 2) if signals_received > 0 else 0.0,
            },
            "orders": {
                "total_orders": total_orders,
                "filled_orders": filled_orders,
                "partially_filled_orders": partially_filled_orders,
                "cancelled_orders": cancelled_orders,
                "expired_orders": expired_orders,
                "fill_rate_pct": round(fill_rate, 2),
                "total_filled_quantity": float(total_filled_qty),
                "turnover": float(quantize_currency(turnover)),
            },
            "trades": {
                "total_trades": filled_orders,
                "filled_orders": filled_orders,
            },
            "simulation_assumptions": {
                "environment": "SIMULATION",
                "disclaimer": "Research simulation metrics only. Not financial advice.",
                "configuration_hash": session.risk_config_hash,
            },
        }

        # Persist report
        file_path = os.path.join(self.storage_dir, f"perf_{session.bot_session_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report
