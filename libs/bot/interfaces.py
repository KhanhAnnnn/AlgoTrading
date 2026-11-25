"""
libs/bot/interfaces.py — Abstract Base Classes & Component Contracts (GĐ29)
Defines standard contracts matching Anil Gaddam's architecture adapted for AlgoTrading.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Dict, Any
from libs.bot.domain import (
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedOrder,
    PortfolioSnapshot,
)


class TradingStrategy(ABC):
    """Abstract interface for all trading strategies."""

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Returns the unique name/identifier of this strategy."""
        pass

    @abstractmethod
    def generate_signals(self, market_data: MarketDataEvent) -> Optional[StrategySignal]:
        """
        Evaluates a market data bar and generates a signal if criteria are satisfied.
        Returns None or StrategySignal.
        """
        pass


class BotDataManager(ABC):
    """Abstract interface for streaming market data ingestion and caching."""

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Optional[MarketDataEvent]:
        """Returns the most recent 1m bar for a given symbol."""
        pass

    @abstractmethod
    def process_bar(self, bar: MarketDataEvent) -> Optional[MarketDataEvent]:
        """Processes an incoming bar, applying revision and finalization filters."""
        pass

    @abstractmethod
    def subscribe(self, symbols: List[str], on_bar_callback: Callable[[MarketDataEvent], None]) -> None:
        """Registers a callback for bar arrival notifications."""
        pass


class BotPortfolioManager(ABC):
    """Abstract interface for capital allocation, position sizing, and risk enforcement."""

    @abstractmethod
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        stop_loss_price: Optional[float] = None
    ) -> float:
        """Calculates quantity of shares/contracts to buy based on portfolio risk rules."""
        pass

    @abstractmethod
    def evaluate_signal(self, signal: StrategySignal, current_price: float) -> SignalDecision:
        """Evaluates whether to accept or reject a strategy signal based on risk boundaries."""
        pass

    @abstractmethod
    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Returns current snapshot of cash, positions, and equity."""
        pass


class SimulationOrderManager(ABC):
    """Abstract interface for managing simulated orders in an isolated sandbox."""

    @abstractmethod
    def submit_order_intent(self, intent: SimulationOrderIntent) -> SimulatedOrder:
        """Converts an intent into a simulated broker order and routes to simulation engine."""
        pass

    @abstractmethod
    def cancel_order(self, simulated_order_id: str) -> bool:
        """Cancels an existing open simulated order."""
        pass

    @abstractmethod
    def get_open_orders(self) -> List[SimulatedOrder]:
        """Retrieves all currently open simulated orders."""
        pass


class TradingBotLifecycle(ABC):
    """Abstract interface for bot state machine and orchestration."""

    @abstractmethod
    def start(self) -> None:
        """Initializes components and begins listening to data feed."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully halts trading, cancels pending intents, and persists state."""
        pass

    @abstractmethod
    def pause(self) -> None:
        """Temporarily pauses signal generation without closing existing positions."""
        pass

    @abstractmethod
    def resume(self) -> None:
        """Resumes active signal generation from paused state."""
        pass

    @abstractmethod
    def get_status(self) -> str:
        """Returns current bot lifecycle state (e.g., STOPPED, RUNNING, PAUSED)."""
        pass
