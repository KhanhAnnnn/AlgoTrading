"""
libs/bot/portfolio/snapshot.py — Portfolio Snapshot Manager & Versioning (GĐ32)
Creates deterministic, checksummed point-in-time snapshots of the simulation portfolio.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import hashlib
import uuid
import copy

from libs.bot.domain import PortfolioSnapshot, SimulatedPosition
from libs.bot.portfolio.accounting import to_decimal, quantize_currency


class PortfolioSnapshotManager:
    """
    Manages generation, versioning, and integrity checksums for portfolio snapshots.
    """

    @staticmethod
    def compute_checksum(
        portfolio_id: str,
        version: int,
        cash: float,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
        state: str,
    ) -> str:
        """Computes SHA-256 integrity checksum across critical portfolio metrics."""
        payload = f"{portfolio_id}:{version}:{cash:.4f}:{equity:.4f}:{realized_pnl:.4f}:{unrealized_pnl:.4f}:{state}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def create_snapshot(
        cls,
        portfolio_id: str,
        bot_session_id: str,
        state: str,
        cash: Decimal,
        reserved_cash: Decimal,
        positions: Dict[str, SimulatedPosition],
        realized_pnl: Decimal,
        peak_equity: Decimal,
        version: int,
        open_orders_count: int = 0,
    ) -> PortfolioSnapshot:
        """
        Creates a new immutable PortfolioSnapshot with Decimal-derived values and checksum.
        """
        cash_dec = to_decimal(cash)
        res_cash_dec = to_decimal(reserved_cash)
        avail_cash_dec = max(Decimal("0.0"), cash_dec - res_cash_dec)
        realized_dec = to_decimal(realized_pnl)

        total_mv = Decimal("0.0")
        total_upnl = Decimal("0.0")
        gross_exp = Decimal("0.0")

        positions_copy: Dict[str, SimulatedPosition] = {}
        for sym, pos in positions.items():
            if abs(pos.qty) > 1e-9:
                mv = to_decimal(pos.market_value)
                upnl = to_decimal(pos.unrealized_pnl)
                total_mv += mv
                total_upnl += upnl
                gross_exp += abs(mv)
                positions_copy[sym] = copy.copy(pos)

        equity_dec = cash_dec + total_mv
        peak_dec = max(to_decimal(peak_equity), equity_dec)

        # Drawdown calculation
        drawdown_pct = Decimal("0.0")
        if peak_dec > Decimal("0"):
            dd_amount = peak_dec - equity_dec
            if dd_amount > Decimal("0"):
                drawdown_pct = dd_amount / peak_dec

        cash_flt = float(quantize_currency(cash_dec))
        equity_flt = float(quantize_currency(equity_dec))
        avail_flt = float(quantize_currency(avail_cash_dec))
        res_flt = float(quantize_currency(res_cash_dec))
        gross_flt = float(quantize_currency(gross_exp))
        realized_flt = float(quantize_currency(realized_dec))
        upnl_flt = float(quantize_currency(total_upnl))
        peak_flt = float(quantize_currency(peak_dec))
        dd_flt = float(drawdown_pct)

        checksum = cls.compute_checksum(
            portfolio_id=portfolio_id,
            version=version,
            cash=cash_flt,
            equity=equity_flt,
            realized_pnl=realized_flt,
            unrealized_pnl=upnl_flt,
            state=state,
        )

        return PortfolioSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            portfolio_id=portfolio_id,
            bot_session_id=bot_session_id,
            timestamp=datetime.now(timezone.utc),
            state=state,
            cash=cash_flt,
            equity=equity_flt,
            available_cash=avail_flt,
            reserved_cash=res_flt,
            gross_exposure=gross_flt,
            peak_equity=peak_flt,
            drawdown_pct=dd_flt,
            positions=positions_copy,
            open_orders_count=open_orders_count,
            realized_pnl=realized_flt,
            unrealized_pnl=upnl_flt,
            checksum=checksum,
            version=version,
            environment="SIMULATION",
        )
