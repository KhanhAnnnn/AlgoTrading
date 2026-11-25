"""
libs/bot/config.py — Trading Configuration & Sanitized Parameters (GĐ29)
Enforces primary timeframe '1m', simulation boundaries, and zero secret storage.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os


@dataclass
class TradingConfig:
    """
    Sanitized Configuration for V2 Paper Trading Bot.
    Guarantees no secret keys/credentials stored in configuration artifacts.
    Enforces strict simulation parameters and 1m primary timeframe.
    """
    bot_name: str = "PaperBotV2"
    strategy_name: str = "MA_CROSS"
    symbols: List[str] = field(default_factory=lambda: ["NVDA", "BTC/USD"])
    timeframe: str = "1m"
    initial_cash: float = 100000.0
    risk_per_trade_pct: float = 0.02
    max_open_positions: int = 5
    dry_run: bool = True
    environment: str = "SIMULATION"
    redpanda_consumer_group: str = "paper-bot-v2-group"
    redpanda_topics: List[str] = field(default_factory=lambda: ["stock-prices", "crypto-bars-1m"])
    require_final_bars: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Disallowed credential fields to prevent accidental leakages
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        """Validates all trading configuration constraints."""
        # 1. Zero secret storage check
        if any([self.api_key, self.secret_key, self.password, self.token]):
            raise ValueError(
                "TradingConfig security violation: API keys, secrets, and credentials "
                "must not be embedded in configuration objects."
            )

        # 2. Strict simulation & dry run check
        if self.environment != "SIMULATION":
            raise ValueError(
                f"Invalid environment: '{self.environment}'. Only 'SIMULATION' is permitted in V2 Paper Bot base design."
            )

        if not self.dry_run:
            raise ValueError(
                "TradingConfig invalid: dry_run must be True. Live trading execution is strictly prohibited."
            )

        # 3. Timeframe validation
        if self.timeframe != "1m":
            raise ValueError(
                f"Unsupported timeframe '{self.timeframe}'. GĐ29 primary timeframe standard is strictly '1m'."
            )

        # 4. Financial parameters validation
        if self.initial_cash <= 0:
            raise ValueError(f"initial_cash must be strictly positive, got {self.initial_cash}")

        if not (0.0001 <= self.risk_per_trade_pct <= 0.10):
            raise ValueError(
                f"risk_per_trade_pct must be between 0.01% and 10.0%, got {self.risk_per_trade_pct}"
            )

        if self.max_open_positions <= 0:
            raise ValueError(f"max_open_positions must be at least 1, got {self.max_open_positions}")

        # 5. Symbols validation
        if not self.symbols:
            raise ValueError("symbols list cannot be empty.")

        for sym in self.symbols:
            if not isinstance(sym, str) or not sym.strip():
                raise ValueError(f"Invalid symbol: '{sym}'")
