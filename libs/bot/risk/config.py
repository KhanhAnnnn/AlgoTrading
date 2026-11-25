"""
libs/bot/risk/config.py — Simulation Risk Configuration & Boundaries (GĐ32)
Defines risk parameters, thresholds, and guard policies with deterministic configuration hashing.
All configurations are explicitly research-oriented simulation boundaries, NOT investment advice.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import hashlib
import json


@dataclass
class RiskConfig:
    """
    Schema-enforced risk boundary configuration.
    Provides safe defaults, toggleable limits, and deterministic SHA-256 configuration hashing.
    """
    risk_configuration_version: str = "1.0.0"
    risk_per_trade_pct: float = 0.02          # 2% equity risk per trade
    max_position_notional: float = 25000.0    # Max USD value per single position
    max_position_qty: float = 10000.0         # Max quantity of shares/contracts per position
    max_symbol_exposure_pct: float = 0.30     # Max 30% total equity in any single symbol
    max_portfolio_exposure_pct: float = 1.00  # Max 100% gross exposure across all positions
    daily_loss_limit_pct: float = 0.05        # 5% max daily loss guard
    max_drawdown_pct: float = 0.10            # 10% max peak-to-trough drawdown lockout
    max_concurrent_positions: int = 5         # Max open positions simultaneously
    max_price_age_seconds: int = 300          # 5 minutes stale price threshold
    allow_short: bool = False                 # Default long-only for simulation safety
    sizing_mode: str = "PERCENT_RISK"         # PERCENT_RISK, FIXED_NOTIONAL, FIXED_QTY
    fixed_notional: float = 5000.0            # Used if sizing_mode == "FIXED_NOTIONAL"
    fixed_qty: float = 10.0                   # Used if sizing_mode == "FIXED_QTY"
    strategy_version_whitelist: List[str] = field(
        default_factory=lambda: ["1.0.0", "1.0", "v1.0.0"]
    )
    environment: str = "SIMULATION"

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        """Enforces schema boundaries and mathematical invariants."""
        if self.environment != "SIMULATION":
            raise ValueError("RiskConfig strictly requires environment='SIMULATION'")
        if not (0.0 < self.risk_per_trade_pct <= 0.50):
            raise ValueError(f"risk_per_trade_pct must be in (0, 0.50], got {self.risk_per_trade_pct}")
        if self.max_position_notional <= 0:
            raise ValueError(f"max_position_notional must be > 0, got {self.max_position_notional}")
        if not (0.0 < self.max_symbol_exposure_pct <= 1.0):
            raise ValueError(f"max_symbol_exposure_pct must be in (0, 1.0], got {self.max_symbol_exposure_pct}")
        if self.max_portfolio_exposure_pct <= 0:
            raise ValueError(f"max_portfolio_exposure_pct must be > 0, got {self.max_portfolio_exposure_pct}")
        if not (0.0 < self.max_drawdown_pct <= 1.0):
            raise ValueError(f"max_drawdown_pct must be in (0, 1.0], got {self.max_drawdown_pct}")
        if self.max_concurrent_positions < 1:
            raise ValueError(f"max_concurrent_positions must be >= 1, got {self.max_concurrent_positions}")
        if self.sizing_mode not in {"PERCENT_RISK", "FIXED_NOTIONAL", "FIXED_QTY"}:
            raise ValueError(f"Invalid sizing_mode: {self.sizing_mode}")

    def compute_hash(self) -> str:
        """Computes deterministic SHA-256 hash of this risk configuration."""
        data = asdict(self)
        # Sort keys for deterministic JSON serialization
        canonical_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
