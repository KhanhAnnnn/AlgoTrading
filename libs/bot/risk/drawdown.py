"""
libs/bot/risk/drawdown.py — Drawdown Monitoring & Risk Lockout Guard (GĐ32)
Tracks peak equity, continuous peak-to-trough equity drawdown,
and triggers automatic fail-closed lockout upon boundary breach.
"""

from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from libs.bot.domain import DrawdownSnapshot, RiskEvent
from libs.bot.portfolio.accounting import to_decimal, quantize_currency

logger = logging.getLogger("drawdown-monitor")


class DrawdownMonitor:
    """
    Monitors portfolio peak equity and calculates drawdown percentage.
    Automatically trips a fail-closed risk lockout if drawdown exceeds threshold.
    """

    def __init__(
        self,
        portfolio_id: str,
        initial_equity: Decimal,
        max_drawdown_pct: Decimal = Decimal("0.10"),
    ):
        self.portfolio_id = portfolio_id
        self.max_drawdown_pct = to_decimal(max_drawdown_pct)
        self.peak_equity = to_decimal(initial_equity)
        self.current_equity = to_decimal(initial_equity)
        self.is_locked = False
        self.lock_reason: Optional[str] = None
        self.events: list[RiskEvent] = []

    def update(self, current_equity: Decimal) -> Tuple[DrawdownSnapshot, Optional[RiskEvent]]:
        """
        Updates equity, calculates drawdown, and triggers lockout if breached.
        Returns (DrawdownSnapshot, Optional[RiskEvent]).
        """
        curr_eq = to_decimal(current_equity)
        self.current_equity = curr_eq

        # Update high-water mark
        if curr_eq > self.peak_equity:
            self.peak_equity = curr_eq

        # Calculate absolute and percentage drawdown
        drawdown_amount = Decimal("0.0")
        drawdown_pct = Decimal("0.0")

        if self.peak_equity > Decimal("0"):
            diff = self.peak_equity - curr_eq
            if diff > Decimal("0"):
                drawdown_amount = diff
                drawdown_pct = diff / self.peak_equity

        risk_event: Optional[RiskEvent] = None

        # Check if drawdown breached maximum threshold
        if drawdown_pct >= self.max_drawdown_pct and not self.is_locked:
            self.is_locked = True
            self.lock_reason = (
                f"DRAWDOWN_BREACH: Drawdown {float(drawdown_pct * 100):.2f}% "
                f"exceeded maximum allowed limit {float(self.max_drawdown_pct * 100):.2f}%"
            )
            risk_event = RiskEvent(
                event_id=f"re_{uuid.uuid4().hex[:12]}",
                portfolio_id=self.portfolio_id,
                timestamp=datetime.now(timezone.utc),
                event_type="DRAWDOWN_LIMIT_BREACHED",
                severity="LOCKOUT",
                reason_code="MAX_DRAWDOWN_EXCEEDED",
                message=self.lock_reason,
                metrics={
                    "peak_equity": float(self.peak_equity),
                    "current_equity": float(curr_eq),
                    "drawdown_amount": float(drawdown_amount),
                    "drawdown_pct": float(drawdown_pct),
                    "max_drawdown_pct": float(self.max_drawdown_pct),
                },
                environment="SIMULATION",
            )
            self.events.append(risk_event)
            logger.warning(f"Portfolio {self.portfolio_id} locked: {self.lock_reason}")

        snapshot = DrawdownSnapshot(
            snapshot_id=f"dd_{uuid.uuid4().hex[:12]}",
            portfolio_id=self.portfolio_id,
            peak_equity=float(quantize_currency(self.peak_equity)),
            current_equity=float(quantize_currency(curr_eq)),
            drawdown_amount=float(quantize_currency(drawdown_amount)),
            drawdown_pct=float(drawdown_pct),
            is_locked=self.is_locked,
            timestamp=datetime.now(timezone.utc),
            environment="SIMULATION",
        )

        return snapshot, risk_event

    def reset_lock(self, operator: str = "TEST_HARNESS") -> None:
        """Resets the lockout state (for controlled recovery testing)."""
        self.is_locked = False
        self.lock_reason = None
        logger.info(f"Drawdown lock for portfolio {self.portfolio_id} reset by {operator}")
