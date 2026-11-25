"""
libs/bot/multibot/resource_policy.py — Multi-Bot Resource & Concurrency Policy (GĐ37)
Defines resource constraints, execution boundaries, queue capacities,
and memory/lag limits for concurrent simulation bots.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


class ConcurrencyLimitExceededError(RuntimeError):
    """Raised when starting a bot would exceed max_concurrent_bots limit."""
    pass


@dataclass
class ResourcePolicy:
    """
    Defines resource allocation and concurrency limits for Multi-Bot Supervisor.
    """
    max_concurrent_bots: int = 10
    max_queue_size_per_bot: int = 1000
    max_processing_lag_seconds: float = 300.0
    shutdown_timeout_seconds: float = 5.0
    max_memory_budget_mb: float = 1024.0
    max_symbols_per_bot: int = 20
    default_initial_cash: float = 100000.0
    environment: str = "SIMULATION"

    def validate(self) -> None:
        """Validates that policy values conform to safe operational bounds."""
        if self.max_concurrent_bots <= 0:
            raise ValueError("max_concurrent_bots must be positive")
        if self.max_queue_size_per_bot <= 0:
            raise ValueError("max_queue_size_per_bot must be positive")
        if self.max_processing_lag_seconds <= 0:
            raise ValueError("max_processing_lag_seconds must be positive")
        if self.shutdown_timeout_seconds <= 0:
            raise ValueError("shutdown_timeout_seconds must be positive")
        if self.max_symbols_per_bot <= 0:
            raise ValueError("max_symbols_per_bot must be positive")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes policy to dictionary representation."""
        return {
            "max_concurrent_bots": self.max_concurrent_bots,
            "max_queue_size_per_bot": self.max_queue_size_per_bot,
            "max_processing_lag_seconds": self.max_processing_lag_seconds,
            "shutdown_timeout_seconds": self.shutdown_timeout_seconds,
            "max_memory_budget_mb": self.max_memory_budget_mb,
            "max_symbols_per_bot": self.max_symbols_per_bot,
            "default_initial_cash": self.default_initial_cash,
            "environment": self.environment,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourcePolicy":
        """Constructs ResourcePolicy from dictionary."""
        return cls(
            max_concurrent_bots=data.get("max_concurrent_bots", 10),
            max_queue_size_per_bot=data.get("max_queue_size_per_bot", 1000),
            max_processing_lag_seconds=data.get("max_processing_lag_seconds", 300.0),
            shutdown_timeout_seconds=data.get("shutdown_timeout_seconds", 5.0),
            max_memory_budget_mb=data.get("max_memory_budget_mb", 1024.0),
            max_symbols_per_bot=data.get("max_symbols_per_bot", 20),
            default_initial_cash=data.get("default_initial_cash", 100000.0),
            environment=data.get("environment", "SIMULATION"),
        )
