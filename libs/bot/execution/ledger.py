"""
libs/bot/execution/ledger.py — Execution Event Ledger & Reconciliation Engine (GĐ33)
Maintains audit trail of all execution actions with full correlation ID chains.
Provides mathematical reconciliation between Orders, Fills, Portfolio Cash, and Positions.
"""

from decimal import Decimal
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import uuid
import os

from libs.bot.domain import SimulatedOrder, SimulatedFill
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal, quantize_currency


@dataclass
class LedgerEntry:
    """Immutable audit record for execution lifecycle events."""
    entry_id: str = field(default_factory=lambda: f"ledg_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = "ORDER_SUBMITTED"
    correlation_id: Dict[str, str] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)
    environment: str = "SIMULATION"


@dataclass
class ReconciliationReport:
    """Formal audit report reconciling orders, fills, and portfolio ledger."""
    status: str  # BALANCED, DISCREPANCY_DETECTED
    reconciled_at: datetime
    total_orders_audited: int
    total_fills_audited: int
    discrepancies: List[str]
    metrics: Dict[str, Any]
    environment: str = "SIMULATION"


class ExecutionLedger:
    """
    Central execution ledger tracking lifecycle events and verifying balance invariants.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir
        self.entries: List[LedgerEntry] = []
        self.ledger_path = os.path.join(storage_dir, "ledger.jsonl") if storage_dir else None
        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)

    def record_event(
        self,
        event_type: str,
        correlation_id: Dict[str, str],
        payload: Dict[str, Any],
    ) -> LedgerEntry:
        """Appends an execution event to the ledger."""
        entry = LedgerEntry(
            event_type=event_type,
            correlation_id=correlation_id,
            payload=payload,
            environment="SIMULATION",
        )
        self.entries.append(entry)
        if self.ledger_path:
            try:
                import json
                with open(self.ledger_path, "a", encoding="utf-8") as f:
                    rec = {
                        "entry_id": entry.entry_id,
                        "timestamp": entry.timestamp.isoformat(),
                        "event_type": entry.event_type,
                        "correlation_id": entry.correlation_id,
                        "payload": entry.payload,
                        "environment": entry.environment,
                    }
                    f.write(json.dumps(rec) + "\n")
            except Exception:
                pass
        return entry

    def reconcile(
        self,
        portfolio: SimulationPortfolioManager,
        orders: List[SimulatedOrder],
        fills: List[SimulatedFill],
        initial_cash: Optional[Decimal] = None,
    ) -> ReconciliationReport:
        """
        Performs three-way mathematical reconciliation:
        1. Order quantity vs cumulative fill quantity.
        2. Net fill quantity vs portfolio position quantity.
        3. Net fill cash flow vs current portfolio cash.
        """
        discrepancies: List[str] = []

        # 1. Order fill quantity reconciliation
        fills_by_order: Dict[str, Decimal] = {}
        for f in fills:
            ord_id = f.simulated_order_id
            fills_by_order[ord_id] = fills_by_order.get(ord_id, Decimal("0.0")) + to_decimal(f.fill_qty)

        for o in orders:
            ord_id = o.simulated_order_id
            cum_fill = fills_by_order.get(ord_id, Decimal("0.0"))
            recorded_filled = to_decimal(o.filled_quantity)
            if abs(cum_fill - recorded_filled) > Decimal("1e-6"):
                discrepancies.append(
                    f"Order {ord_id} mismatch: cumulative fills {cum_fill} != recorded filled_qty {recorded_filled}"
                )

        # 2. Position quantity reconciliation
        net_qty_by_symbol: Dict[str, Decimal] = {}
        for f in fills:
            sym = f.symbol
            q = to_decimal(f.fill_qty)
            if f.side.upper() == "BUY":
                net_qty_by_symbol[sym] = net_qty_by_symbol.get(sym, Decimal("0.0")) + q
            elif f.side.upper() == "SELL":
                net_qty_by_symbol[sym] = net_qty_by_symbol.get(sym, Decimal("0.0")) - q

        for sym, net_q in net_qty_by_symbol.items():
            pos = portfolio.positions.get_position(sym)
            pos_qty = to_decimal(pos.qty) if pos else Decimal("0.0")
            if abs(net_q - pos_qty) > Decimal("1e-6"):
                discrepancies.append(
                    f"Symbol {sym} position mismatch: net fill qty {net_q} != portfolio pos qty {pos_qty}"
                )

        # 3. Cash balance reconciliation
        # Expected Cash = InitialCash - Sum(BUY Notional + BUY Fees) + Sum(SELL Notional - SELL Fees)
        init_c = to_decimal(initial_cash or Decimal("100000.0"))
        net_cash_delta = Decimal("0.0")
        total_fees = Decimal("0.0")

        for f in fills:
            notional = to_decimal(f.fill_qty) * to_decimal(f.fill_price)
            fee = to_decimal(f.fee)
            total_fees += fee
            if f.side.upper() == "BUY":
                net_cash_delta -= (notional + fee)
            elif f.side.upper() == "SELL":
                net_cash_delta += (notional - fee)

        expected_cash = init_c + net_cash_delta
        actual_cash = portfolio.cash

        if abs(expected_cash - actual_cash) > Decimal("0.01"):
            discrepancies.append(
                f"Cash balance discrepancy: expected {expected_cash} != actual {actual_cash}"
            )

        status = "BALANCED" if len(discrepancies) == 0 else "DISCREPANCY_DETECTED"
        return ReconciliationReport(
            status=status,
            reconciled_at=datetime.now(timezone.utc),
            total_orders_audited=len(orders),
            total_fills_audited=len(fills),
            discrepancies=discrepancies,
            metrics={
                "expected_cash": float(quantize_currency(expected_cash)),
                "actual_cash": float(quantize_currency(actual_cash)),
                "total_fees": float(quantize_currency(total_fees)),
                "net_cash_delta": float(quantize_currency(net_cash_delta)),
            },
            environment="SIMULATION",
        )
