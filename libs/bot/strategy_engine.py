"""
libs/bot/strategy_engine.py — Strategy Execution Engine (GĐ31)
Coordinates event-driven evaluation of finalized 1m bars from PaperBotDataAccess
through registered strategies, signal validation, deduplication, and persistence.
Strictly decoupled from order execution or capital allocation.
"""

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
import time
import logging

from libs.bot.domain import MarketDataEvent, StrategySignal
from libs.bot.strategies.base import BaseStrategy
from libs.bot.strategy_registry import StrategyRegistry, default_registry
from libs.bot.signal_validator import SignalValidator
from libs.bot.signal_store import SignalStore
from libs.bot.data_access import PaperBotDataAccess

logger = logging.getLogger("strategy-engine")


class StrategyExecutionEngine:
    """
    Core Strategy Execution Engine for AlgoTrading V2.
    Event-driven pipeline:
    Finalized MarketDataEvent -> Input Validation -> Strategy Evaluation
    -> Signal Validation -> Deduplication -> StrategySignal -> Persistence.
    """

    def __init__(
        self,
        data_access: Optional[PaperBotDataAccess] = None,
        registry: Optional[StrategyRegistry] = None,
        validator: Optional[SignalValidator] = None,
        store: Optional[SignalStore] = None,
    ):
        self.data_access = data_access or PaperBotDataAccess()
        self.registry = registry or default_registry
        self.validator = validator or SignalValidator()
        self.store = store or SignalStore()

        # Active strategy instances: (strategy_id, symbol) -> BaseStrategy
        self._active_strategies: Dict[str, BaseStrategy] = {}
        # Subscriber callbacks for generated actionable signals
        self._signal_subscribers: List[Callable[[StrategySignal], None]] = []

        # Operational telemetry counters
        self.bars_evaluated = 0
        self.signals_generated = 0
        self.duplicate_evaluations = 0
        self.invalid_inputs = 0
        self.is_running = False

    def add_strategy_instance(self, strategy: BaseStrategy, symbols: List[str]) -> None:
        """Attaches a strategy instance to manage signals for specified symbols."""
        for sym in symbols:
            key = f"{strategy.strategy_id}:{sym}"
            self._active_strategies[key] = strategy
            logger.info("Attached strategy '%s' for symbol '%s'", strategy.strategy_id, sym)

    def attach_strategy(self, strategy_id: str, symbols: List[str], **kwargs) -> Optional[BaseStrategy]:
        """Instantiates strategy from registry and attaches to specified symbols."""
        try:
            strat = self.registry.create_instance(strategy_id, **kwargs)
            if strat:
                self.add_strategy_instance(strat, symbols)
                return strat
        except Exception as e:
            logger.warning("Could not auto-attach strategy '%s': %s", strategy_id, e)
        return None

    def subscribe_signals(self, callback: Callable[[StrategySignal], None]) -> None:
        """Registers a callback for StrategySignal emissions."""
        self._signal_subscribers.append(callback)

    def process_bar(self, bar: MarketDataEvent) -> List[StrategySignal]:
        """
        Processes a single finalized MarketDataEvent through all matching strategies.
        Guarantees deterministic, sequential evaluation.
        """
        self.bars_evaluated += 1
        emitted_signals: List[StrategySignal] = []
        symbol = bar.symbol

        # Identify all active strategies listening to this symbol
        matching = [
            (k, strat) for k, strat in self._active_strategies.items()
            if k.endswith(f":{symbol}")
        ]

        for key, strategy in matching:
            t0 = time.perf_counter()

            # 1. Input validation
            if not strategy.validate_input(bar):
                self.invalid_inputs += 1
                continue

            # 2. Strategy evaluation
            try:
                raw_sig = strategy.generate_signals(bar)
            except Exception as e:
                logger.error("Strategy '%s' evaluation exception on %s: %s", strategy.strategy_id, symbol, e)
                continue

            if raw_sig is None:
                continue

            # 3. Validation & Deduplication
            is_new, validated_sig, action = self.validator.validate_and_deduplicate(raw_sig)

            if action == "DUPLICATE_SUPPRESSED":
                self.duplicate_evaluations += 1
                continue

            # 4. Persistence
            self.store.save_signal(validated_sig)
            self.signals_generated += 1
            emitted_signals.append(validated_sig)

            # 5. Dispatch to subscribers if actionable (BUY or SELL)
            if validated_sig.signal_type in ["BUY", "SELL"]:
                for cb in self._signal_subscribers:
                    try:
                        cb(validated_sig)
                    except Exception as cb_e:
                        logger.error("Signal subscriber error: %s", cb_e)

        return emitted_signals

    def start(self) -> None:
        """Wires data access callbacks and marks running."""
        self.is_running = True
        self.data_access.subscribe(symbols=[], timeframe="1m", callback=self.process_bar)
        logger.info("StrategyExecutionEngine started.")

    def stop(self) -> None:
        """Gracefully halts engine."""
        self.is_running = False
        logger.info("StrategyExecutionEngine stopped.")

    def reset_state(self, symbol: Optional[str] = None) -> None:
        """Resets all active strategy states and validator caches."""
        for strat in self._active_strategies.values():
            strat.reset_state(symbol)
        if symbol is None:
            self.validator = SignalValidator()

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns engine telemetry snapshot."""
        return {
            "is_running": self.is_running,
            "active_strategies_count": len(self._active_strategies),
            "bars_evaluated": self.bars_evaluated,
            "signals_generated": self.signals_generated,
            "duplicate_evaluations": self.duplicate_evaluations,
            "invalid_inputs": self.invalid_inputs,
            "total_validated_signals": self.validator.total_emitted,
        }
