"""
libs/bot/backtesting/results.py — Backtest Results & Deterministic Fingerprints (GĐ36)
Encapsulates complete backtest execution outcomes, serializes equity curves,
computes deterministic economic fingerprints, and verifies reproducibility between runs.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import hashlib
import json

from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.dataset import DatasetManifest


@dataclass
class BacktestResult:
    """
    Complete output artifact of a Backtest execution.
    Computes an immutable economic fingerprint for reproducibility auditing.
    """
    run_id: str
    config: BacktestConfig
    metrics: Dict[str, Any]
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    drawdown_curve: List[Dict[str, Any]] = field(default_factory=list)
    orders: List[Dict[str, Any]] = field(default_factory=list)
    fills: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    positions: List[Dict[str, Any]] = field(default_factory=list)
    bars: List[Dict[str, Any]] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    portfolio_transactions: List[Dict[str, Any]] = field(default_factory=list)
    closed_trades: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    manifest: Optional[DatasetManifest] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "COMPLETED"
    environment: str = "SIMULATION"

    def compute_deterministic_fingerprint(self) -> str:
        """
        Computes an invariant SHA-256 fingerprint representing purely economic and trading outcomes:
        - final equity, cash, realized/unrealized PnL
        - total fees, slippage, trade count, fill count
        - final position balances
        - dataset checksum
        Ignores non-deterministic run IDs, host machine timestamps, and execution durations.
        """
        m = self.metrics
        economic_state = {
            "strategy_id": self.config.strategy_id,
            "strategy_version": self.config.strategy_version,
            "symbols": sorted(self.config.symbols),
            "dataset_checksum": self.manifest.checksum_sha256 if self.manifest else "",
            "final_equity": round(float(m.get("final_equity", 0.0)), 2),
            "net_pnl": round(float(m.get("net_pnl", 0.0)), 2),
            "realized_pnl": round(float(m.get("realized_pnl", 0.0)), 2),
            "unrealized_pnl": round(float(m.get("unrealized_pnl", 0.0)), 2),
            "net_return_pct": round(float(m.get("net_return_pct", 0.0)), 4),
            "total_fees": round(float(m.get("total_fees", 0.0)), 2),
            "total_slippage": round(float(m.get("total_slippage", 0.0)), 2),
            "total_orders": int(m.get("total_orders", 0)),
            "filled_orders": int(m.get("filled_orders", 0)),
            "total_fills": int(m.get("total_fills", 0)),
            "total_trades": int(m.get("total_trades", 0)),
            "positions": sorted(
                [
                    {
                        "symbol": p.get("symbol"),
                        "qty": float(p.get("qty", 0.0)),
                        "cost_basis": round(float(p.get("cost_basis", 0.0)), 2),
                    }
                    for p in self.positions
                ],
                key=lambda x: x["symbol"],
            ),
        }
        canonical_str = json.dumps(economic_state, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def compare(self, other: "BacktestResult") -> Dict[str, Any]:
        """
        Verifies if two independent backtest runs produced identical economic results.
        """
        fp1 = self.compute_deterministic_fingerprint()
        fp2 = other.compute_deterministic_fingerprint()

        identical = (fp1 == fp2)
        diffs = []
        if not identical:
            for k in ["final_equity", "net_pnl", "realized_pnl", "total_orders", "total_fills", "total_trades"]:
                v1 = self.metrics.get(k)
                v2 = other.metrics.get(k)
                if v1 != v2:
                    diffs.append({"metric": k, "run1": v1, "run2": v2})

        return {
            "is_economically_identical": identical,
            "fingerprint_run1": fp1,
            "fingerprint_run2": fp2,
            "differences": diffs,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes complete result to JSON-friendly dictionary."""
        return {
            "run_id": self.run_id,
            "config": self.config.to_dict(),
            "metrics": self.metrics,
            "deterministic_fingerprint": self.compute_deterministic_fingerprint(),
            "orders_count": len(self.orders),
            "fills_count": len(self.fills),
            "equity_points_count": len(self.equity_curve),
            "closed_trades_count": len(self.closed_trades),
            "positions": self.positions,
            "dataset": self.manifest.to_dict() if self.manifest and hasattr(self.manifest, "to_dict") else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "environment": self.environment,
        }
