"""
libs/bot/multibot/dispatcher.py — Market Data Fan-Out Dispatcher (GĐ37)
Central router consuming market data events from Redpanda/synthetic sources
and fanning them out to per-bot bounded queues with non-blocking backpressure isolation.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any
import logging

from libs.bot.domain import MarketDataEvent
from libs.bot.multibot.subscriptions import SubscriptionManager

logger = logging.getLogger("multibot-dispatcher")


class QueueOverflowError(Exception):
    """Raised when a bot's bounded event queue overflows."""
    pass


class V2MarketDataDispatcher:
    """
    Central Market Data Fan-Out Dispatcher.
    Ingests 1m final MarketDataEvents and routes them strictly to subscribed bots.
    Ensures that a slow or paused bot does NOT block or stall processing of healthy bots.
    """

    def __init__(
        self,
        subscription_manager: Optional[SubscriptionManager] = None,
        max_queue_size_per_bot: int = 1000,
    ):
        self.subscription_manager = subscription_manager or SubscriptionManager()
        self.max_queue_size = max_queue_size_per_bot

        # bot_id -> deque of MarketDataEvent
        self._bot_queues: Dict[str, deque] = {}
        # bot_id -> last_processed_event_id
        self._bot_cursors: Dict[str, str] = {}
        # bot_id -> Set[event_id] for deduplication
        self._bot_seen_events: Dict[str, Set[str]] = {}
        # (bot_id, symbol) -> last bar timestamp for temporal ordering verification
        self._bot_symbol_timestamps: Dict[tuple, datetime] = {}

        # Telemetry
        self.total_received: int = 0
        self.total_dispatched: int = 0
        self.total_dropped: int = 0
        self.total_duplicates: int = 0
        self._bot_stats: Dict[str, Dict[str, int]] = {}

        # Reliability remediation: GĐ37 queue overflow fail-closed tracking
        self._gap_blocked_bots: Set[str] = set()
        self._overflow_callback: Optional[Any] = None

    def set_overflow_callback(self, callback: Any) -> None:
        """Registers a callback (bot_id, event) invoked when queue overflow occurs."""
        self._overflow_callback = callback

    def is_bot_blocked(self, bot_id: str) -> bool:
        """Checks if a bot is currently blocked due to a data gap / queue overflow."""
        return bot_id in self._gap_blocked_bots

    def reconcile_data_gap(self, bot_id: str, missing_events: List[MarketDataEvent]) -> bool:
        """
        Reconciles a data gap by enqueuing missing events in temporal order
        and restoring the bot from DATA_GAP_BLOCKED state.
        """
        q = self._get_queue(bot_id)
        seen = self._bot_seen_events.get(bot_id, set())
        for event in missing_events:
            if event.event_id not in seen:
                q.append(event)
                seen.add(event.event_id)
                ev_ts = getattr(event, "event_time", None) or getattr(event, "timestamp", None)
                if ev_ts is not None:
                    self._bot_symbol_timestamps[(bot_id, event.symbol)] = ev_ts
        self._gap_blocked_bots.discard(bot_id)
        logger.info(f"Reconciled data gap for bot '{bot_id}' with {len(missing_events)} events. Bot unblocked.")
        return True

    def _get_queue(self, bot_id: str) -> deque:
        """Returns or creates a bounded FIFO queue for a bot."""
        if bot_id not in self._bot_queues:
            self._bot_queues[bot_id] = deque(maxlen=self.max_queue_size)
            self._bot_seen_events[bot_id] = set()
            self._bot_stats[bot_id] = {
                "enqueued": 0,
                "drained": 0,
                "dropped": 0,
                "duplicates": 0,
            }
        return self._bot_queues[bot_id]

    def register_bot(self, bot_id: str) -> None:
        """Initializes queue and telemetry for a newly activated bot."""
        self._get_queue(bot_id)

    def deregister_bot(self, bot_id: str) -> None:
        """Cleans up in-memory queues and cursors when a bot stops."""
        self._bot_queues.pop(bot_id, None)
        self._bot_seen_events.pop(bot_id, None)
        for key in list(self._bot_symbol_timestamps.keys()):
            if key[0] == bot_id:
                self._bot_symbol_timestamps.pop(key, None)

    def dispatch_event(self, event: MarketDataEvent) -> Dict[str, str]:
        """
        Fans out a single MarketDataEvent to all actively subscribed bots.
        Returns a dictionary mapping bot_id -> dispatch status.
        Status values: 'ENQUEUED', 'DROPPED_QUEUE_FULL', 'DUPLICATE', 'OUT_OF_ORDER'.
        """
        self.total_received += 1
        results: Dict[str, str] = {}

        subscribed_bots = self.subscription_manager.get_subscribed_bots(
            symbol=event.symbol,
            timeframe=event.timeframe,
        )

        for bot_id in subscribed_bots:
            q = self._get_queue(bot_id)
            seen = self._bot_seen_events[bot_id]
            stats = self._bot_stats[bot_id]

            # 0. Check if bot is already blocked due to un-reconciled data gap
            if bot_id in self._gap_blocked_bots:
                results[bot_id] = "DATA_GAP_BLOCKED"
                self.total_dropped += 1
                stats["dropped"] += 1
                logger.debug(f"Bot '{bot_id}' is DATA_GAP_BLOCKED. Event {event.event_id} dropped to avoid processing broken sequence.")
                continue

            # 1. Deduplication check per bot
            if event.event_id in seen:
                results[bot_id] = "DUPLICATE"
                self.total_duplicates += 1
                stats["duplicates"] += 1
                logger.debug(f"Dispatcher dropped duplicate event {event.event_id} for bot {bot_id}")
                continue

            # 2. Per-symbol temporal ordering check per bot
            ts_key = (bot_id, event.symbol)
            last_ts = self._bot_symbol_timestamps.get(ts_key)
            ev_ts = getattr(event, "event_time", None) or getattr(event, "timestamp", None)
            if last_ts is not None and ev_ts is not None and ev_ts < last_ts:
                results[bot_id] = "OUT_OF_ORDER"
                self.total_dropped += 1
                stats["dropped"] += 1
                logger.warning(
                    f"Out of order bar received for bot {bot_id}, symbol {event.symbol}: "
                    f"current={ev_ts.isoformat()}, last={last_ts.isoformat()}"
                )
                continue

            # 3. Check queue capacity (non-blocking backpressure isolation)
            if len(q) >= self.max_queue_size:
                results[bot_id] = "DROPPED_QUEUE_FULL"
                self.total_dropped += 1
                stats["dropped"] += 1
                # Fail-closed transition: mark bot as DATA_GAP_BLOCKED to prevent trading on broken data
                self._gap_blocked_bots.add(bot_id)
                if self._overflow_callback:
                    try:
                        self._overflow_callback(bot_id, event)
                    except Exception as cb_err:
                        logger.error(f"Error in overflow callback for bot '{bot_id}': {cb_err}")
                logger.warning(
                    f"Queue overflow for bot '{bot_id}' (depth={len(q)}/{self.max_queue_size}). "
                    f"Bot marked DATA_GAP_BLOCKED. Dropping event {event.event_id} to protect peer bots."
                )
                continue

            # 4. Enqueue successfully
            q.append(event)
            seen.add(event.event_id)
            if ev_ts is not None:
                self._bot_symbol_timestamps[ts_key] = ev_ts
            results[bot_id] = "ENQUEUED"
            self.total_dispatched += 1
            stats["enqueued"] += 1

        return results

    def get_next_event(self, bot_id: str) -> Optional[MarketDataEvent]:
        """Pops and returns the oldest pending event for the given bot."""
        q = self._bot_queues.get(bot_id)
        if not q:
            return None
        event = q.popleft()
        if bot_id in self._bot_stats:
            self._bot_stats[bot_id]["drained"] += 1
        return event

    def peek_next_event(self, bot_id: str) -> Optional[MarketDataEvent]:
        """Peeks at the next pending event without dequeuing."""
        q = self._bot_queues.get(bot_id)
        if not q or len(q) == 0:
            return None
        return q[0]

    def ack_event(self, bot_id: str, event_id: str) -> None:
        """Updates durable processing cursor for the bot."""
        self._bot_cursors[bot_id] = event_id

    def get_cursor(self, bot_id: str) -> Optional[str]:
        """Returns the last acknowledged event ID for a bot."""
        return self._bot_cursors.get(bot_id)

    def get_queue_depth(self, bot_id: str) -> int:
        """Returns the current pending queue depth for a bot."""
        q = self._bot_queues.get(bot_id)
        return len(q) if q else 0

    def get_telemetry(self) -> Dict[str, Any]:
        """Compiles dispatcher metrics and per-bot queue statuses."""
        return {
            "total_received": self.total_received,
            "total_dispatched": self.total_dispatched,
            "total_dropped": self.total_dropped,
            "total_duplicates": self.total_duplicates,
            "active_queues_count": len(self._bot_queues),
            "queue_depths": {b_id: len(q) for b_id, q in self._bot_queues.items()},
            "bot_stats": dict(self._bot_stats),
        }
