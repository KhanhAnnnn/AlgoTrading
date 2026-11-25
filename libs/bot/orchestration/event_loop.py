"""
libs/bot/orchestration/event_loop.py — 1-Minute Event-Driven Processing Loop (GĐ34)
Coordinates sequential, look-ahead-free processing of 1m MarketDataEvents.
Enforces bounded queue backpressure, idempotency journaling, and broker matching.
"""

from typing import List, Dict, Any, Optional
from collections import deque
from datetime import datetime, timezone
import time
import logging

from libs.bot.domain import (
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedFill,
)
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.bot.orchestration.event_journal import BotEventJournal
from libs.bot.orchestration.health import BotHealthMonitor

logger = logging.getLogger("bot-event-loop")


class QueueOverflowError(Exception):
    """Raised when the event queue capacity is exceeded (backpressure breach)."""
    pass


class BotEventLoop:
    """
    Sequential single-writer event processor ensuring strict chronological ordering
    and zero look-ahead bias between signal generation and order fill simulation.
    """

    def __init__(
        self,
        strategy_engine: StrategyExecutionEngine,
        decision_engine: SignalDecisionEngine,
        simulation_broker: SimulationBroker,
        journal: BotEventJournal,
        health_monitor: BotHealthMonitor,
        max_queue_size: int = 1000,
    ):
        self.strategy_engine = strategy_engine
        self.decision_engine = decision_engine
        self.simulation_broker = simulation_broker
        self.journal = journal
        self.health_monitor = health_monitor
        self.max_queue_size = max_queue_size

        self._queue: deque[MarketDataEvent] = deque()
        self.is_paused: bool = False

    def enqueue_event(self, bar: MarketDataEvent) -> bool:
        """
        Enqueues an incoming 1m market data event.
        Enforces backpressure limits and basic schema/finality guards.
        """
        if bar.environment != "SIMULATION":
            raise ValueError(f"Security error: event {bar.event_id} is not tagged SIMULATION")

        if not bar.is_final:
            logger.debug(f"Rejecting provisional unfinalized bar: {bar.bar_key}")
            return False

        if len(self._queue) >= self.max_queue_size:
            logger.error(f"Event loop queue overflow: {len(self._queue)} >= {self.max_queue_size}")
            self.health_monitor.record_error("QUEUE_OVERFLOW_BACKPRESSURE_LIMIT")
            raise QueueOverflowError(f"Queue capacity of {self.max_queue_size} events exceeded")

        self._queue.append(bar)
        self.health_monitor.queue_depth = len(self._queue)
        return True

    def process_next_event(self) -> Optional[Dict[str, Any]]:
        """
        Processes the next event in the queue through the complete 5-step pipeline:
        1. Broker fill matching (executes prior orders on current bar).
        2. Strategy engine bar evaluation (generates signals on current bar).
        3. Risk & Decision engine (validates signals, generates order intents).
        4. Broker order placement (places orders into WORKING state for next bars).
        5. Journal commit & health updates.
        """
        if not self._queue:
            return None

        if self.is_paused:
            logger.debug("Event loop is PAUSED. Processing suspended.")
            return None

        bar = self._queue.popleft()
        self.health_monitor.queue_depth = len(self._queue)
        start_t = time.perf_counter()

        # Deduplication check
        if self.journal.is_processed(bar.bar_key, bar.event_id):
            logger.debug(f"Skipping already journaled bar: {bar.bar_key}")
            return {"status": "SKIPPED_DUPLICATE", "bar_key": bar.bar_key}

        # Step 1: Match and fill existing pending orders from previous bars
        fills: List[SimulatedFill] = self.simulation_broker.process_bar(bar)

        # Step 2: Evaluate strategy indicators and generate new analytical signals
        raw_signals = self.strategy_engine.process_bar(bar)
        signals: List[StrategySignal] = []
        if isinstance(raw_signals, list):
            signals = raw_signals
        elif raw_signals is not None:
            signals = [raw_signals]

        decisions: List[SignalDecision] = []
        intents: List[SimulationOrderIntent] = []

        # Step 3 & 4: For each actionable signal, evaluate risk and generate order intent
        for sig in signals:
            if sig and sig.signal_type in {"BUY", "SELL"}:
                decision, intent = self.decision_engine.evaluate(
                    signal=sig,
                    reference_price=bar.close,
                    source_bar=bar,
                )
                decisions.append(decision)
                if decision.status == "ACCEPTED" and intent:
                    intents.append(intent)
                    try:
                        self.simulation_broker.submit_intent(intent)
                    except Exception as e:
                        logger.error(f"Failed to submit intent {intent.intent_id}: {e}")
                        self.health_monitor.record_error(str(e))

        # Step 5: Journal commit & telemetry
        latency_ms = (time.perf_counter() - start_t) * 1000.0
        self.journal.record_processed_event(
            bar_key=bar.bar_key,
            event_id=bar.event_id,
            status="PROCESSED",
            signals_generated=len(signals),
            fills_generated=len(fills),
        )
        self.health_monitor.record_event_processed(latency_ms)

        return {
            "status": "PROCESSED",
            "bar_key": bar.bar_key,
            "fills_generated": len(fills),
            "signals": signals,
            "signal": signals[0] if signals else None,
            "decisions": decisions,
            "decision": decisions[0] if decisions else None,
            "intents": intents,
            "intent": intents[0] if intents else None,
            "latency_ms": latency_ms,
        }

    def drain_queue(self) -> int:
        """Processes all pending events in the queue until empty."""
        count = 0
        while self._queue and not self.is_paused:
            res = self.process_next_event()
            if res and res.get("status") == "PROCESSED":
                count += 1
        return count
