"""
libs/bot/strategies/base.py — Enhanced Trading Strategy Base Class (GĐ31)
Extends TradingStrategy ABC with standardized metadata, configuration schema,
required indicators, warmup management, and deterministic signal contracts.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import hashlib
import json

from libs.bot.interfaces import TradingStrategy
from libs.bot.domain import MarketDataEvent, StrategySignal


class BaseStrategy(TradingStrategy, ABC):
    """
    Standardized Base Strategy for Paper Trading Bot V2.
    Strategies only consume MarketDataEvent and indicator outputs.
    Direct access to Kafka, Redpanda, or broker execution APIs is strictly forbidden.
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_name: str,
        strategy_version: str = "1.0.0",
        configuration: Optional[Dict[str, Any]] = None,
        required_timeframe: str = "1m",
        required_warmup_bars: int = 20,
    ):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.strategy_version = strategy_version
        self.configuration = configuration or {}
        self.required_timeframe = required_timeframe
        self.required_warmup_bars = required_warmup_bars
        self._configuration_hash = self._compute_config_hash()

    def get_strategy_name(self) -> str:
        return self.strategy_name

    def get_strategy_id(self) -> str:
        return self.strategy_id

    def get_strategy_version(self) -> str:
        return self.strategy_version

    def get_configuration_hash(self) -> str:
        return self._configuration_hash

    def _compute_config_hash(self) -> str:
        """Computes deterministic SHA256 hash of strategy configuration."""
        raw = json.dumps(self.configuration, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    @abstractmethod
    def configuration_schema(self) -> Dict[str, Any]:
        """Returns JSON schema definition for strategy parameters."""
        pass

    @property
    @abstractmethod
    def required_indicators(self) -> List[str]:
        """Returns list of indicator IDs required by this strategy."""
        pass

    def validate_input(self, bar: MarketDataEvent) -> bool:
        """Validates bar compatibility with strategy requirements."""
        if bar.timeframe != self.required_timeframe:
            return False
        if bar.environment != "SIMULATION":
            return False
        return True

    @abstractmethod
    def reset_state(self, symbol: Optional[str] = None) -> None:
        """Resets internal state for all symbols or a specific symbol."""
        pass

    @abstractmethod
    def generate_signals(self, market_data: MarketDataEvent) -> StrategySignal:
        """Evaluates bar and returns a deterministic StrategySignal."""
        pass
