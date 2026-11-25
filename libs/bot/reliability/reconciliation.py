"""
libs/bot/reliability/reconciliation.py — Financial & Ledger Balance Reconciliation Engine (GĐ39)
Verifies mathematical balance equality, zero duplicate fills, PositionBook integrity,
and execution ledger idempotency.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import math
import logging

from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.domain import SimulatedOrder, SimulatedFill

logger = logging.getLogger("reconciliation-engine")


@dataclass
class ReconciliationReport:
    """Outcome of financial and execution balance audit."""
    is_balanced: bool
    cash_balanced: bool
    positions_balanced: bool
    zero_duplicate_fills: bool
    zero_duplicate_transactions: bool
    discrepancies: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class SimulationReconciliationEngine:
    """
    Audits the financial balance equation and ledger integrity:
    Cash + Reserved Cash == Initial Cash + Realized PnL - Total Fees
    """

    TOLERANCE = 1e-4

    @classmethod
    def audit_portfolio(
        cls,
        portfolio: SimulationPortfolioManager,
        fills: Optional[List[SimulatedFill]] = None,
        orders: Optional[List[SimulatedOrder]] = None,
    ) -> ReconciliationReport:
        discrepancies: List[str] = []

        snap = portfolio.get_portfolio_snapshot()
        initial_cash = float(getattr(snap, "initial_cash", getattr(portfolio, "initial_cash", 100000.0)))
        cash = float(snap.cash)
        reserved_cash = float(snap.reserved_cash)
        realized_pnl = float(snap.realized_pnl)
        total_fees = float(getattr(snap, "total_fees", getattr(portfolio, "total_fees", 0.0)))
        total_cost_basis = sum(float(getattr(p, "cost_basis", 0.0)) for p in snap.positions.values())

        # 1. Cash Balance Equation Audit
        # Semantics:
        # - cash: Total cash in portfolio (includes unreserved and reserved cash)
        # - available_cash: Uncommitted cash free for new orders (cash - reserved_cash)
        # - reserved_cash: Earmarked cash for pending open orders (subset of cash)
        # - total_cost_basis: Sum of (qty * avg_entry_price) across all active positions
        # To avoid double-counting reserved_cash (which is already part of cash):
        # Actual Total = Cash + Total Cost Basis of Open Positions
        # Expected Total = Initial Cash + Realized PnL - Total Fees
        # Equivalently: Available Cash + Reserved Cash + Cost Basis == Initial Cash + Realized PnL - Total Fees
        expected_cash_total = initial_cash + realized_pnl - total_fees
        actual_cash_total = cash + total_cost_basis
        cash_diff = abs(actual_cash_total - expected_cash_total)

        cash_balanced = cash_diff <= cls.TOLERANCE
        if not cash_balanced:
            discrepancies.append(
                f"CASH_MISMATCH: Actual (Cash+Reserved)={actual_cash_total:.4f} != "
                f"Expected (Init+PnL-Fees)={expected_cash_total:.4f} (diff={cash_diff:.6f})"
            )

        # 2. Position Book vs Fills Audit
        positions_balanced = True
        zero_dup_fills = True
        zero_dup_txs = True

        if fills is not None:
            # Check duplicate fills
            fill_ids = [f.fill_id for f in fills if hasattr(f, "fill_id")]
            if len(fill_ids) != len(set(fill_ids)):
                zero_dup_fills = False
                discrepancies.append(f"DUPLICATE_FILLS: Found duplicate fill IDs in fill history ({len(fill_ids)} total vs {len(set(fill_ids))} unique)")

            # Check net position quantities
            net_quantities: Dict[str, float] = {}
            for f in fills:
                sym = f.symbol
                qty = float(f.fill_qty) if hasattr(f, "fill_qty") else float(f.quantity)
                side = f.side if hasattr(f, "side") else "BUY"
                if sym not in net_quantities:
                    net_quantities[sym] = 0.0
                if side == "BUY":
                    net_quantities[sym] += qty
                elif side == "SELL":
                    net_quantities[sym] -= qty

            all_symbols = set(snap.positions.keys()) | set(net_quantities.keys())
            for sym in all_symbols:
                expected_pos_qty = net_quantities.get(sym, 0.0)
                actual_pos_qty = float(snap.positions[sym].quantity) if sym in snap.positions else 0.0
                if abs(expected_pos_qty - actual_pos_qty) > cls.TOLERANCE:
                    positions_balanced = False
                    discrepancies.append(
                        f"POSITION_MISMATCH: Symbol {sym} actual quantity {actual_pos_qty} != expected from fills {expected_pos_qty}"
                    )

        # 3. Ledger Transactions Check
        txs = getattr(portfolio, "transactions", []) or getattr(portfolio, "_transactions", [])
        if txs:
            tx_ids = [getattr(t, "transaction_id", str(i)) for i, t in enumerate(txs)]
            if len(tx_ids) != len(set(tx_ids)):
                zero_dup_txs = False
                discrepancies.append("DUPLICATE_TRANSACTIONS: Found duplicate transaction IDs in ledger")

        is_balanced = cash_balanced and positions_balanced and zero_dup_fills and zero_dup_txs

        return ReconciliationReport(
            is_balanced=is_balanced,
            cash_balanced=cash_balanced,
            positions_balanced=positions_balanced,
            zero_duplicate_fills=zero_dup_fills,
            zero_duplicate_transactions=zero_dup_txs,
            discrepancies=discrepancies,
            metrics={
                "initial_cash": initial_cash,
                "cash": cash,
                "reserved_cash": reserved_cash,
                "realized_pnl": realized_pnl,
                "total_fees": total_fees,
                "unrealized_pnl": float(snap.unrealized_pnl),
                "total_equity": float(getattr(snap, "total_equity", getattr(snap, "equity", 0.0))),
                "cash_diff": cash_diff,
                "discrepancies_count": len(discrepancies),
            },
        )
