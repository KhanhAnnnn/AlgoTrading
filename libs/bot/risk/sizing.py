"""
libs/bot/risk/sizing.py — Position Sizing Engine (GĐ32)
Calculates quantitative position sizes using the 2% risk rule, fixed notional, or fixed quantity.
Enforces non-lossy Decimal precision, fractional asset preservation, zero-stop guards,
and buying power constraints without broker calls.
"""

from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone

from libs.bot.domain import StrategySignal
from libs.bot.risk.config import RiskConfig
from libs.bot.portfolio.accounting import (
    to_decimal,
    quantize_qty,
    quantize_currency,
    validate_price_freshness,
)


@dataclass
class SizingResult:
    """Quantitative output and risk audit trace of position sizing calculation."""
    is_valid: bool = False
    proposed_quantity: Decimal = Decimal("0.0")
    proposed_notional: Decimal = Decimal("0.0")
    estimated_exposure: Decimal = Decimal("0.0")
    risk_calculation_trace: Dict[str, Any] = field(default_factory=dict)
    rejection_reason: Optional[str] = None
    reason_code: Optional[str] = None


class PositionSizingEngine:
    """
    Independent engine calculating allowable order quantity and notional value.
    Explicitly operates in simulation mode with strict Decimal precision.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()

    def calculate_size(
        self,
        symbol: str,
        signal: StrategySignal,
        reference_price: Union[float, Decimal],
        equity: Union[float, Decimal],
        available_cash: Union[float, Decimal],
        stop_loss_price: Optional[Union[float, Decimal]] = None,
        price_time: Optional[datetime] = None,
        reference_time: Optional[datetime] = None,
        asset_class: str = "STOCKS",
        quantity_precision: Optional[int] = None,
    ) -> SizingResult:
        """
        Calculates position size based on configured sizing mode and risk boundaries.
        Returns SizingResult with detailed audit trace.
        """
        # 1. Price Validation & Freshness
        is_fresh, freshness_err = validate_price_freshness(
            price=reference_price,
            price_time=price_time or signal.signal_time,
            max_age_seconds=self.config.max_price_age_seconds,
            reference_time=reference_time,
        )
        if not is_fresh:
            code = "STALE_REFERENCE_PRICE" if "STALE" in (freshness_err or "") else "INVALID_REFERENCE_PRICE"
            return SizingResult(
                is_valid=False,
                rejection_reason=f"Price validation failed: {freshness_err}",
                reason_code=code,
                risk_calculation_trace={"freshness_error": freshness_err},
            )

        ref_p = to_decimal(reference_price)
        eq = to_decimal(equity)
        avail_cash = to_decimal(available_cash)

        if eq <= Decimal("0"):
            return SizingResult(
                is_valid=False,
                rejection_reason="Portfolio equity is non-positive",
                reason_code="NON_POSITIVE_EQUITY",
            )

        if avail_cash <= Decimal("0"):
            return SizingResult(
                is_valid=False,
                rejection_reason="Insufficient available cash (0.0 or negative)",
                reason_code="INSUFFICIENT_SIMULATED_CASH",
            )

        # Determine precision based on asset class or override
        if quantity_precision is not None:
            decimals = quantity_precision
        elif "BTC" in symbol or "ETH" in symbol or "/" in symbol or asset_class == "CRYPTO":
            decimals = 4
        else:
            decimals = 2

        trace: Dict[str, Any] = {
            "symbol": symbol,
            "reference_price": float(ref_p),
            "equity": float(eq),
            "available_cash": float(avail_cash),
            "sizing_mode": self.config.sizing_mode,
            "precision_decimals": decimals,
        }

        # 2. Sizing calculation by mode
        raw_qty = Decimal("0.0")

        if self.config.sizing_mode == "PERCENT_RISK":
            # 2% Risk Rule
            risk_pct = to_decimal(self.config.risk_per_trade_pct)
            risk_budget = eq * risk_pct
            trace["risk_per_trade_pct"] = float(risk_pct)
            trace["risk_budget"] = float(risk_budget)

            if stop_loss_price is not None:
                try:
                    stop_p = to_decimal(stop_loss_price)
                except ValueError:
                    return SizingResult(
                        is_valid=False,
                        rejection_reason="Invalid stop loss price format",
                        reason_code="INVALID_STOP_PRICE",
                    )
                stop_distance = abs(ref_p - stop_p)
                trace["stop_loss_price"] = float(stop_p)
                trace["stop_distance"] = float(stop_distance)

                if stop_distance == Decimal("0"):
                    return SizingResult(
                        is_valid=False,
                        rejection_reason="Stop loss distance is zero, causing infinite position risk",
                        reason_code="ZERO_STOP_DISTANCE",
                        risk_calculation_trace=trace,
                    )
                raw_qty = risk_budget / stop_distance
            else:
                # Without explicit stop loss, cap allocation to risk budget / price or symbol exposure
                max_symbol_exp = eq * to_decimal(self.config.max_symbol_exposure_pct)
                allocation = min(risk_budget, max_symbol_exp)
                raw_qty = allocation / ref_p
                trace["stop_loss_price"] = None
                trace["unhedged_allocation"] = float(allocation)

        elif self.config.sizing_mode == "FIXED_NOTIONAL":
            notional = to_decimal(self.config.fixed_notional)
            raw_qty = notional / ref_p
            trace["fixed_notional"] = float(notional)

        elif self.config.sizing_mode == "FIXED_QTY":
            raw_qty = to_decimal(self.config.fixed_qty)
            trace["fixed_qty"] = float(raw_qty)

        # 3. Guard: Quantity must be strictly positive
        if raw_qty <= Decimal("0"):
            return SizingResult(
                is_valid=False,
                rejection_reason="Calculated quantity is zero or negative",
                reason_code="NON_POSITIVE_QUANTITY",
                risk_calculation_trace=trace,
            )

        # 4. Cap by available simulated cash (Buying Power)
        max_cash_qty = avail_cash / ref_p
        trace["max_cash_qty"] = float(max_cash_qty)

        if raw_qty > max_cash_qty:
            trace["capped_by_cash"] = True
            raw_qty = max_cash_qty

        # 5. Cap by Configured Position Limits
        max_notional = to_decimal(self.config.max_position_notional)
        max_notional_qty = max_notional / ref_p
        if raw_qty > max_notional_qty:
            trace["capped_by_max_notional"] = True
            raw_qty = max_notional_qty

        max_pos_qty = to_decimal(self.config.max_position_qty)
        if raw_qty > max_pos_qty:
            trace["capped_by_max_pos_qty"] = True
            raw_qty = max_pos_qty

        # 6. Quantize with conservative ROUND_DOWN (preserving fractional quantities)
        final_qty = quantize_qty(raw_qty, decimals=decimals)
        final_notional = quantize_currency(final_qty * ref_p)

        trace["final_qty"] = float(final_qty)
        trace["final_notional"] = float(final_notional)

        # 7. Minimum Viable Size Check: Do not force minimum-one-quantity
        if final_qty <= Decimal("0"):
            return SizingResult(
                is_valid=False,
                rejection_reason="Position size below minimum quantize precision",
                reason_code="INSUFFICIENT_SIMULATED_CASH",
                risk_calculation_trace=trace,
            )

        if final_notional > avail_cash:
            return SizingResult(
                is_valid=False,
                rejection_reason=f"Required notional {final_notional} exceeds available cash {avail_cash}",
                reason_code="INSUFFICIENT_SIMULATED_CASH",
                risk_calculation_trace=trace,
            )

        return SizingResult(
            is_valid=True,
            proposed_quantity=final_qty,
            proposed_notional=final_notional,
            estimated_exposure=final_notional,
            risk_calculation_trace=trace,
            reason_code="SIZING_ACCEPTED",
        )
