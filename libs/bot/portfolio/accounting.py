"""
libs/bot/portfolio/accounting.py — Precision Decimal Portfolio Accounting Engine (GĐ32)
Implements all financial math for AlgoTrading V2.0 using Python Decimal arithmetic.
Prevents floating-point precision loss and handles fractional quantities, zero positions, and P&L.
"""

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, InvalidOperation
from typing import Optional, Union, Dict, Any
from datetime import datetime, timezone
import math


def to_decimal(val: Union[float, int, str, Decimal, None]) -> Decimal:
    """Safely converts a numeric value to Decimal, rejecting NaN, Inf, and None."""
    if val is None:
        raise ValueError("Cannot convert None to Decimal")
    if isinstance(val, Decimal):
        if val.is_nan() or val.is_infinite():
            raise ValueError(f"Invalid Decimal value: {val}")
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Invalid float value: {val}")
        return Decimal(str(val))
    try:
        dec = Decimal(str(val))
        if dec.is_nan() or dec.is_infinite():
            raise ValueError(f"Invalid numeric string: {val}")
        return dec
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Failed to convert {val} to Decimal: {e}")


def quantize_currency(val: Union[Decimal, float], decimals: int = 2) -> Decimal:
    """Quantizes currency values to standard cents precision using ROUND_HALF_UP."""
    d = to_decimal(val)
    step = Decimal("10") ** (-decimals)
    return d.quantize(step, rounding=ROUND_HALF_UP)


def quantize_qty(val: Union[Decimal, float], decimals: int = 4) -> Decimal:
    """Quantizes asset quantity using conservative ROUND_DOWN to prevent over-allocation."""
    d = to_decimal(val)
    step = Decimal("10") ** (-decimals)
    return d.quantize(step, rounding=ROUND_DOWN)


def calculate_market_value(qty: Union[Decimal, float], price: Union[Decimal, float]) -> Decimal:
    """Calculates position market value: Quantity * ValuationPrice."""
    q = to_decimal(qty)
    p = to_decimal(price)
    return q * p


def calculate_cost_basis(qty: Union[Decimal, float], avg_entry_price: Union[Decimal, float]) -> Decimal:
    """Calculates position cost basis: Quantity * AvgEntryPrice."""
    q = to_decimal(qty)
    p = to_decimal(avg_entry_price)
    return q * p


def calculate_unrealized_pnl(market_value: Union[Decimal, float], cost_basis: Union[Decimal, float]) -> Decimal:
    """Calculates unrealized P&L: MarketValue - CostBasis."""
    mv = to_decimal(market_value)
    cb = to_decimal(cost_basis)
    return mv - cb


def calculate_portfolio_equity(
    cash: Union[Decimal, float],
    positions_market_value: Union[Decimal, float]
) -> Decimal:
    """Calculates total portfolio equity: Cash + Sum(Market Value of Positions)."""
    c = to_decimal(cash)
    pmv = to_decimal(positions_market_value)
    return c + pmv


def calculate_available_cash(
    cash: Union[Decimal, float],
    reserved_cash: Union[Decimal, float]
) -> Decimal:
    """Calculates uncommitted cash: Cash - ReservedCash."""
    c = to_decimal(cash)
    r = to_decimal(reserved_cash)
    avail = c - r
    return max(Decimal("0.0"), avail)


def calculate_realized_pnl(
    closed_qty: Union[Decimal, float],
    avg_entry_price: Union[Decimal, float],
    exit_price: Union[Decimal, float],
    is_short: bool = False
) -> Decimal:
    """
    Calculates realized P&L on closing or trimming a position.
    Long: (exit_price - avg_entry_price) * closed_qty
    Short: (avg_entry_price - exit_price) * closed_qty
    """
    q = to_decimal(closed_qty)
    entry_p = to_decimal(avg_entry_price)
    exit_p = to_decimal(exit_price)

    if q <= Decimal("0"):
        return Decimal("0.0")

    if is_short:
        return (entry_p - exit_p) * q
    return (exit_p - entry_p) * q


def calculate_new_weighted_avg_price(
    current_qty: Union[Decimal, float],
    current_avg_price: Union[Decimal, float],
    added_qty: Union[Decimal, float],
    fill_price: Union[Decimal, float]
) -> Decimal:
    """
    Calculates updated weighted average entry price when expanding an existing position.
    NewAvg = ((CurrentQty * CurrentAvgPrice) + (AddedQty * FillPrice)) / (CurrentQty + AddedQty)
    """
    q1 = to_decimal(current_qty)
    p1 = to_decimal(current_avg_price)
    q2 = to_decimal(added_qty)
    p2 = to_decimal(fill_price)

    total_qty = q1 + q2
    if total_qty == Decimal("0"):
        return Decimal("0.0")

    total_cost = (q1 * p1) + (q2 * p2)
    return total_cost / total_qty


def validate_price_freshness(
    price: Optional[Union[float, Decimal]],
    price_time: Optional[datetime] = None,
    max_age_seconds: int = 300,
    reference_time: Optional[datetime] = None
) -> tuple[bool, Optional[str]]:
    """
    Validates whether a price is numeric, positive, non-zero, and within the freshness window.
    Returns (is_valid, error_code).
    """
    if price is None:
        return False, "MISSING_PRICE"
    try:
        p_dec = to_decimal(price)
    except (ValueError, TypeError):
        return False, "INVALID_PRICE_FORMAT"

    if p_dec <= Decimal("0"):
        return False, "NON_POSITIVE_PRICE"

    if price_time is not None:
        ref_time = reference_time or datetime.now(timezone.utc)
        if price_time.tzinfo is None:
            price_time = price_time.replace(tzinfo=timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        age = (ref_time - price_time).total_seconds()
        if age > max_age_seconds:
            return False, f"STALE_PRICE_AGE_{int(age)}S"
        if age < -300:  # Allow 5m clock skew
            return False, "FUTURE_TIMESTAMP_PRICE"

    return True, None
