"""
libs/bot/portfolio/positions.py — Simulated Position Book & Valuation (GĐ32)
Manages asset positions with Decimal precision, supporting fractional quantities,
cost-basis tracking, position closing, and real-time mark-to-market valuation.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone
import copy

from libs.bot.domain import SimulatedPosition
from libs.bot.portfolio.accounting import (
    to_decimal,
    quantize_currency,
    quantize_qty,
    calculate_market_value,
    calculate_cost_basis,
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_new_weighted_avg_price,
    validate_price_freshness,
)


class PositionBook:
    """
    Manages a collection of virtual asset positions for a simulation portfolio.
    Enforces non-lossy Decimal math and handles zero-quantity and fractional positions.
    """

    def __init__(self):
        self._positions: Dict[str, SimulatedPosition] = {}

    def get_position(self, symbol: str) -> Optional[SimulatedPosition]:
        """Returns the simulated position for a symbol, if active."""
        return self._positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Returns True if an open position exists with non-zero quantity."""
        pos = self._positions.get(symbol)
        return pos is not None and abs(pos.qty) > 1e-9

    def get_all_positions(self) -> Dict[str, SimulatedPosition]:
        """Returns a shallow copy of all current positions."""
        return copy.copy(self._positions)

    def get_active_positions(self) -> List[SimulatedPosition]:
        """Returns all positions with non-zero quantity."""
        return [p for p in self._positions.values() if abs(p.qty) > 1e-9]

    def get_active_positions_count(self) -> int:
        """Returns the number of active open positions."""
        return len(self.get_active_positions())

    def update_valuation(
        self,
        symbol: str,
        current_price: Union[float, Decimal],
        price_time: Optional[datetime] = None,
        max_age_seconds: int = 300,
    ) -> bool:
        """
        Updates the mark-to-market valuation for an existing position using latest price.
        Returns True if updated successfully, False if price is invalid or stale.
        """
        pos = self._positions.get(symbol)
        if not pos or abs(pos.qty) < 1e-9:
            return False

        is_valid, err = validate_price_freshness(current_price, price_time, max_age_seconds)
        if not is_valid:
            return False

        p_dec = to_decimal(current_price)
        q_dec = to_decimal(pos.qty)
        avg_p_dec = to_decimal(pos.avg_entry_price)

        mv_dec = calculate_market_value(q_dec, p_dec)
        cb_dec = calculate_cost_basis(q_dec, avg_p_dec)
        upnl_dec = calculate_unrealized_pnl(mv_dec, cb_dec)

        pos.current_price = float(p_dec)
        pos.market_value = float(mv_dec)
        pos.cost_basis = float(cb_dec)
        pos.unrealized_pnl = float(upnl_dec)
        pos.updated_at = datetime.now(timezone.utc)
        return True

    def record_fill(
        self,
        symbol: str,
        side: str,
        qty: Union[float, Decimal],
        fill_price: Union[float, Decimal],
        fee: Union[float, Decimal] = 0.0,
    ) -> Decimal:
        """
        Updates position state upon a simulated fill event.
        Calculates realized P&L when trimming or closing a position.
        Returns realized P&L (Decimal).
        """
        q_fill = to_decimal(qty)
        p_fill = to_decimal(fill_price)
        f_fill = to_decimal(fee)

        if q_fill <= Decimal("0") or p_fill <= Decimal("0"):
            raise ValueError(f"Invalid fill parameters: qty={qty}, price={fill_price}")

        pos = self._positions.get(symbol)
        realized_pnl_delta = Decimal("0.0")

        if pos is None:
            # New position
            if side == "BUY":
                mv = q_fill * p_fill
                cb = q_fill * p_fill
                self._positions[symbol] = SimulatedPosition(
                    symbol=symbol,
                    qty=float(q_fill),
                    avg_entry_price=float(p_fill),
                    current_price=float(p_fill),
                    cost_basis=float(cb),
                    market_value=float(mv),
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    updated_at=datetime.now(timezone.utc),
                    environment="SIMULATION",
                )
            elif side == "SELL":
                # Simulated short position
                mv = -(q_fill * p_fill)
                cb = q_fill * p_fill
                self._positions[symbol] = SimulatedPosition(
                    symbol=symbol,
                    qty=float(-q_fill),
                    avg_entry_price=float(p_fill),
                    current_price=float(p_fill),
                    cost_basis=float(cb),
                    market_value=float(mv),
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    updated_at=datetime.now(timezone.utc),
                    environment="SIMULATION",
                )
            return Decimal("0.0")

        # Existing position update
        curr_q = to_decimal(pos.qty)
        curr_avg = to_decimal(pos.avg_entry_price)

        if side == "BUY":
            if curr_q >= Decimal("0"):
                # Increasing Long
                new_avg = calculate_new_weighted_avg_price(curr_q, curr_avg, q_fill, p_fill)
                new_q = curr_q + q_fill
                pos.qty = float(new_q)
                pos.avg_entry_price = float(new_avg)
                pos.current_price = float(p_fill)
                pos.market_value = float(new_q * p_fill)
                pos.cost_basis = float(new_q * new_avg)
                pos.unrealized_pnl = pos.market_value - pos.cost_basis
                pos.updated_at = datetime.now(timezone.utc)
            else:
                # Covering Short
                covered_qty = min(abs(curr_q), q_fill)
                realized_gain = (curr_avg - p_fill) * covered_qty
                realized_pnl_delta = realized_gain
                new_q = curr_q + q_fill
                pos.realized_pnl += float(realized_gain)
                if abs(new_q) < Decimal("1e-9"):
                    pos.qty = 0.0
                    pos.market_value = 0.0
                    pos.cost_basis = 0.0
                    pos.unrealized_pnl = 0.0
                else:
                    pos.qty = float(new_q)
                    pos.current_price = float(p_fill)
                    pos.market_value = float(new_q * p_fill)
                    pos.cost_basis = float(abs(new_q) * curr_avg)
                    pos.unrealized_pnl = pos.cost_basis - abs(pos.market_value)
                pos.updated_at = datetime.now(timezone.utc)

        elif side == "SELL":
            if curr_q > Decimal("0"):
                # Selling Long
                sold_qty = min(curr_q, q_fill)
                realized_gain = (p_fill - curr_avg) * sold_qty
                realized_pnl_delta = realized_gain
                new_q = curr_q - q_fill
                pos.realized_pnl += float(realized_gain)
                if abs(new_q) < Decimal("1e-9"):
                    pos.qty = 0.0
                    pos.market_value = 0.0
                    pos.cost_basis = 0.0
                    pos.unrealized_pnl = 0.0
                else:
                    pos.qty = float(new_q)
                    pos.current_price = float(p_fill)
                    pos.market_value = float(new_q * p_fill)
                    pos.cost_basis = float(new_q * curr_avg)
                    pos.unrealized_pnl = pos.market_value - pos.cost_basis
                pos.updated_at = datetime.now(timezone.utc)
            else:
                # Expanding Short
                new_avg = calculate_new_weighted_avg_price(abs(curr_q), curr_avg, q_fill, p_fill)
                new_q = curr_q - q_fill
                pos.qty = float(new_q)
                pos.avg_entry_price = float(new_avg)
                pos.current_price = float(p_fill)
                pos.market_value = float(new_q * p_fill)
                pos.cost_basis = float(abs(new_q) * new_avg)
                pos.unrealized_pnl = pos.cost_basis - abs(pos.market_value)
                pos.updated_at = datetime.now(timezone.utc)

        # Clean up zero positions
        if abs(pos.qty) < 1e-9:
            pos.qty = 0.0
            pos.market_value = 0.0
            pos.cost_basis = 0.0
            pos.unrealized_pnl = 0.0

        return realized_pnl_delta

    def get_total_market_value(self) -> Decimal:
        """Returns the sum of market values of all positions."""
        total = Decimal("0.0")
        for p in self._positions.values():
            if abs(p.qty) > 1e-9:
                total += to_decimal(p.market_value)
        return total

    def get_gross_exposure(self) -> Decimal:
        """Returns the absolute sum of market values across all positions."""
        total = Decimal("0.0")
        for p in self._positions.values():
            if abs(p.qty) > 1e-9:
                total += abs(to_decimal(p.market_value))
        return total

    def get_total_unrealized_pnl(self) -> Decimal:
        """Returns the sum of unrealized P&L across all positions."""
        total = Decimal("0.0")
        for p in self._positions.values():
            if abs(p.qty) > 1e-9:
                total += to_decimal(p.unrealized_pnl)
        return total

    def get_total_realized_pnl(self) -> Decimal:
        """Returns the sum of realized P&L across all positions."""
        total = Decimal("0.0")
        for p in self._positions.values():
            total += to_decimal(p.realized_pnl)
        return total
