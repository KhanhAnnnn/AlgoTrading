"""
libs/bot/execution/portfolio_adapter.py — Portfolio Execution Adapter (GĐ33)
Applies simulated order fills to GĐ32 SimulationPortfolioManager with strict idempotency guards.
Prevents double-counting of cash, positions, or reservations.
"""

from decimal import Decimal
from typing import Set, Optional
import logging

from libs.bot.domain import SimulatedFill, SimulatedOrder
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal, quantize_currency

logger = logging.getLogger("portfolio-execution-adapter")


class PortfolioExecutionAdapter:
    """
    Coordinates application of SimulatedFill events to the SimulationPortfolioManager.
    Guarantees exactly-once execution per fill identifier.
    """

    def __init__(self, portfolio: SimulationPortfolioManager):
        self.portfolio = portfolio
        self._applied_fill_ids: Set[str] = set()

    def is_fill_applied(self, fill_id: str) -> bool:
        """Checks if a fill has already been processed."""
        return fill_id in self._applied_fill_ids

    def apply_fill(
        self,
        fill: SimulatedFill,
        reference_price: Optional[float] = None,
    ) -> bool:
        """
        Applies a simulated fill to portfolio cash, positions, and ledger.
        Returns True if applied, False if skipped as duplicate.
        """
        fill_id = fill.simulated_fill_id
        if self.is_fill_applied(fill_id):
            logger.warning(f"Idempotency guard: Fill {fill_id} already applied to portfolio {self.portfolio.portfolio_id}. Skipping.")
            return False

        q = to_decimal(fill.fill_qty)
        p = to_decimal(fill.fill_price)
        f = to_decimal(fill.fee)
        side = fill.side.upper()
        symbol = fill.symbol

        if side == "BUY":
            cost = (q * p) + f
            # Release reservation corresponding to filled quantity
            ref_p = to_decimal(reference_price or fill.fill_price)
            reserved_to_release = q * ref_p
            self.portfolio.release_cash(reserved_to_release, reference_id=fill_id)

            # Deduct actual cash
            self.portfolio._cash -= cost

            # Update position in portfolio
            self.portfolio.positions.record_fill(
                symbol=symbol,
                side="BUY",
                qty=q,
                fill_price=p,
                fee=f,
            )

            # Ledger transaction
            self.portfolio._record_transaction(
                transaction_type="SIMULATED_FILL_BUY",
                amount=-cost,
                description=f"BUY fill {q} {symbol} @ {p} USD (fee={f})",
                reference_id=fill_id,
            )

        elif side == "SELL":
            proceeds = (q * p) - f
            # Add actual cash
            self.portfolio._cash += proceeds

            # Update position in portfolio & accumulate realized P&L
            realized_pnl_delta = self.portfolio.positions.record_fill(
                symbol=symbol,
                side="SELL",
                qty=q,
                fill_price=p,
                fee=f,
            )
            self.portfolio._realized_pnl += realized_pnl_delta

            # Ledger transaction
            self.portfolio._record_transaction(
                transaction_type="SIMULATED_FILL_SELL",
                amount=proceeds,
                description=f"SELL fill {q} {symbol} @ {p} USD (fee={f}, pnl={realized_pnl_delta})",
                reference_id=fill_id,
            )
        else:
            raise ValueError(f"Unsupported fill side: {side}")

        self._applied_fill_ids.add(fill_id)
        # Touch version to invalidate cached snapshots
        self.portfolio._version += 1
        return True

    def release_order_reservation(
        self,
        order: SimulatedOrder,
        reference_price: float,
    ) -> Decimal:
        """
        Releases reserved cash for remaining unfilled quantity upon order cancellation/expiration.
        """
        rem_qty = to_decimal(order.remaining_quantity)
        if rem_qty <= Decimal("0.0") or order.side.upper() != "BUY":
            return Decimal("0.0")

        ref_p = to_decimal(reference_price)
        reserved_to_release = rem_qty * ref_p
        self.portfolio.release_cash(reserved_to_release, reference_id=order.simulated_order_id)
        return reserved_to_release
