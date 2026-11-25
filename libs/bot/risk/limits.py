"""
libs/bot/risk/limits.py — Simulation Risk Limits Engine (GĐ32)
Evaluates Position Limits, Cash & Exposure Checks, Portfolio Guards, and Signal Guards.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from libs.bot.domain import StrategySignal, MarketDataEvent, SimulatedPosition
from libs.bot.risk.config import RiskConfig
from libs.bot.portfolio.accounting import to_decimal


class RiskLimitsEngine:
    """
    Evaluates order proposals and signals against strict risk limits and boundaries.
    Generates standardized machine-readable reason codes for all limit breaches.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()

    def check_position_limits(
        self,
        symbol: str,
        proposed_qty: Decimal,
        proposed_notional: Decimal,
        current_pos: Optional[SimulatedPosition],
        equity: Decimal,
        gross_exposure: Decimal,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Evaluates position-level and portfolio-wide exposure limits.
        Returns (is_passed, breach_codes, metrics).
        """
        breach_codes: List[str] = []
        metrics: Dict[str, Any] = {}

        eq = to_decimal(equity)
        notional = to_decimal(proposed_notional)
        qty = to_decimal(proposed_qty)

        curr_qty = to_decimal(current_pos.qty) if current_pos else Decimal("0.0")
        curr_mv = to_decimal(current_pos.market_value) if current_pos else Decimal("0.0")

        new_total_qty = curr_qty + qty
        new_total_mv = curr_mv + notional

        # 1. Max Position Value (Notional)
        max_notional = to_decimal(self.config.max_position_notional)
        if new_total_mv > max_notional:
            breach_codes.append(f"EXCEEDS_MAX_POSITION_NOTIONAL ({new_total_mv} > {max_notional})")

        # 2. Max Position Quantity
        max_qty = to_decimal(self.config.max_position_qty)
        if new_total_qty > max_qty:
            breach_codes.append(f"EXCEEDS_MAX_POSITION_QTY ({new_total_qty} > {max_qty})")

        # 3. Per-Symbol Concentration / Exposure Limit
        if eq > Decimal("0"):
            max_sym_pct = to_decimal(self.config.max_symbol_exposure_pct)
            new_sym_pct = new_total_mv / eq
            metrics["symbol_exposure_pct"] = float(new_sym_pct)
            if new_sym_pct > max_sym_pct:
                breach_codes.append(f"EXCEEDS_SYMBOL_EXPOSURE_LIMIT ({float(new_sym_pct*100):.1f}% > {float(max_sym_pct*100):.1f}%)")

        # 4. Total Portfolio Gross Exposure Limit
        if eq > Decimal("0"):
            max_port_pct = to_decimal(self.config.max_portfolio_exposure_pct)
            new_gross_exp = to_decimal(gross_exposure) + notional
            new_gross_pct = new_gross_exp / eq
            metrics["portfolio_gross_exposure_pct"] = float(new_gross_pct)
            if new_gross_pct > max_port_pct:
                breach_codes.append(f"EXCEEDS_PORTFOLIO_EXPOSURE_LIMIT ({float(new_gross_pct*100):.1f}% > {float(max_port_pct*100):.1f}%)")

        return len(breach_codes) == 0, breach_codes, metrics

    def check_portfolio_guards(
        self,
        symbol: str,
        has_existing_position: bool,
        active_positions_count: int,
        is_drawdown_locked: bool,
        current_drawdown_pct: Decimal = Decimal("0.0"),
        daily_loss_pct: Decimal = Decimal("0.0"),
    ) -> Tuple[bool, List[str]]:
        """
        Evaluates portfolio-level health guards: concurrent positions, daily loss, drawdown lock.
        """
        breach_codes: List[str] = []

        # 1. Max concurrent positions (only restricts opening a brand new symbol position)
        if not has_existing_position and active_positions_count >= self.config.max_concurrent_positions:
            breach_codes.append(f"MAX_CONCURRENT_POSITIONS_REACHED ({active_positions_count} >= {self.config.max_concurrent_positions})")

        # 2. Drawdown Lockout
        if is_drawdown_locked:
            breach_codes.append("DRAWDOWN_LIMIT_BREACHED_LOCKOUT_ACTIVE")

        # 3. Daily Loss Limit
        if daily_loss_pct >= to_decimal(self.config.daily_loss_limit_pct):
            breach_codes.append(f"DAILY_LOSS_LIMIT_BREACHED ({float(daily_loss_pct*100):.1f}% >= {float(self.config.daily_loss_limit_pct*100):.1f}%)")

        return len(breach_codes) == 0, breach_codes

    def check_signal_guards(
        self,
        signal: StrategySignal,
        source_bar: Optional[MarketDataEvent] = None,
        seen_signal_ids: Optional[set] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Evaluates signal metadata, environment tag, finality, and duplicate status.
        """
        breach_codes: List[str] = []

        # 1. SIMULATION environment enforcement
        if signal.environment != "SIMULATION":
            breach_codes.append("NON_SIMULATION_ENVIRONMENT")

        # 2. Actionable signal type
        if signal.signal_type not in {"BUY", "SELL"}:
            breach_codes.append(f"UNSUPPORTED_SIGNAL_TYPE_{signal.signal_type}")

        # 3. Duplicate signal check
        if seen_signal_ids is not None and signal.signal_id in seen_signal_ids:
            breach_codes.append("DUPLICATE_SIGNAL")

        # 4. Strategy version compatibility
        if signal.strategy_version not in self.config.strategy_version_whitelist:
            breach_codes.append(f"INCOMPATIBLE_STRATEGY_VERSION_{signal.strategy_version}")

        # 5. Source Bar validation
        if source_bar is not None:
            if not source_bar.is_final:
                breach_codes.append("UNFINALIZED_SOURCE_BAR")
            if source_bar.bar_revision != signal.source_bar_revision:
                breach_codes.append("SOURCE_BAR_REVISION_MISMATCH")

        return len(breach_codes) == 0, breach_codes
