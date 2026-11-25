"""
libs/bot/backtesting/config.py — Backtest Configuration & Deterministic Hashing (GĐ36)
Defines parameters, risk guardrails, warmup policies, and session constraints for historical backtesting.
All configurations are explicitly research-oriented simulation boundaries, strictly environment='SIMULATION'.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import hashlib
import json
import uuid

from libs.bot.risk.config import RiskConfig


@dataclass
class BacktestConfig:
    """
    Immutable specification for a backtesting execution run.
    Guarantees reproducibility via deterministic config hashing and seed control.
    """
    backtest_run_id: str = field(default_factory=lambda: f"bt_{uuid.uuid4().hex[:12]}")
    strategy_id: str = "MA_CROSS_1M"
    strategy_version: str = "1.0.0"
    symbols: List[str] = field(default_factory=lambda: ["NVDA"])
    asset_classes: Dict[str, str] = field(default_factory=lambda: {"NVDA": "STOCKS", "BTC/USD": "CRYPTO"})
    timeframe: str = "1m"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    initial_simulated_cash: float = 100000.0
    risk_config: Optional[RiskConfig] = None
    execution_config: Dict[str, Any] = field(default_factory=dict)
    fee_model: str = "DEFAULT"
    slippage_model: str = "DEFAULT"
    volume_participation_rate: float = 0.10
    market_session_policy: str = "STRICT_HOURS"  # STRICT_HOURS (9:30-16:00 EST for stocks) or ALL_HOURS
    dataset_reference: str = ""
    warmup_policy: str = "AUTO"  # AUTO, FIXED, NONE
    warmup_bars_count: int = 50
    seed: Optional[int] = 42
    environment: str = "SIMULATION"

    def __post_init__(self):
        if self.risk_config is None:
            self.risk_config = RiskConfig(environment="SIMULATION")
        self.validate()

    def validate(self) -> None:
        """Enforces schema boundaries and invariants."""
        if self.environment != "SIMULATION":
            raise ValueError(f"BacktestConfig requires environment='SIMULATION', got '{self.environment}'")
        if not self.symbols:
            raise ValueError("BacktestConfig requires at least one symbol")
        if self.initial_simulated_cash <= 0:
            raise ValueError(f"initial_simulated_cash must be > 0, got {self.initial_simulated_cash}")
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValueError(f"start_time ({self.start_time}) must be strictly before end_time ({self.end_time})")
        if not (0.0 < self.volume_participation_rate <= 1.0):
            raise ValueError(f"volume_participation_rate must be in (0, 1.0], got {self.volume_participation_rate}")
        if self.warmup_bars_count < 0:
            raise ValueError(f"warmup_bars_count must be >= 0, got {self.warmup_bars_count}")

    def compute_config_hash(self) -> str:
        """
        Computes a deterministic SHA-256 hash across the operational configuration parameters.
        Ignores transient IDs (like backtest_run_id).
        """
        hash_dict = {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbols": sorted(self.symbols),
            "timeframe": self.timeframe,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "initial_simulated_cash": float(self.initial_simulated_cash),
            "fee_model": self.fee_model,
            "slippage_model": self.slippage_model,
            "volume_participation_rate": float(self.volume_participation_rate),
            "market_session_policy": self.market_session_policy,
            "warmup_bars_count": int(self.warmup_bars_count),
            "seed": self.seed,
            "environment": self.environment,
            "risk_config_hash": self.risk_config.compute_hash() if self.risk_config else "",
        }
        canonical_json = json.dumps(hash_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes configuration to dictionary."""
        return {
            "backtest_run_id": self.backtest_run_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbols": self.symbols,
            "asset_classes": self.asset_classes,
            "timeframe": self.timeframe,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "initial_simulated_cash": self.initial_simulated_cash,
            "fee_model": self.fee_model,
            "slippage_model": self.slippage_model,
            "volume_participation_rate": self.volume_participation_rate,
            "market_session_policy": self.market_session_policy,
            "dataset_reference": self.dataset_reference,
            "warmup_policy": self.warmup_policy,
            "warmup_bars_count": self.warmup_bars_count,
            "seed": self.seed,
            "execution_config": self.execution_config,
            "config_hash": self.compute_config_hash(),
            "environment": self.environment,
        }
