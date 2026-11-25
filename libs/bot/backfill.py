"""
libs/bot/backfill.py — Historical Backfill & Deterministic Replay Engine (GĐ30)
Fetches historical 1m bars via Read-Only Alpaca client or offline fixtures,
merges without duplicates, replays by event-time, and guarantees zero writes to natural topics.
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
import logging
import json
import os

from libs.bot.domain import MarketDataEvent
from libs.bot.normalization import MarketDataNormalizer
from libs.bot.storage import MarketDataStore

logger = logging.getLogger("historical-backfill")


class HistoricalBackfillManager:
    """
    Manages historical 1m bar backfilling and deterministic event-time replay.
    Strict Invariants:
    1. Provenance is always 'HISTORICAL_BACKFILL' or 'FIXTURE'.
    2. Zero writes to Redpanda natural market topics.
    3. Replay of identical input produces deterministic output sequence.
    """

    def __init__(self, store: Optional[MarketDataStore] = None):
        self.store = store or MarketDataStore()

    def backfill_from_alpaca_readonly(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        api_client: Optional[Any] = None,
    ) -> List[MarketDataEvent]:
        """
        Backfills 1-minute bars using Alpaca Read-Only historical client.
        Guarantees: No broker execution, Read-Only GET endpoints only.
        """
        if start >= end:
            raise ValueError(f"Start time ({start}) must be strictly before end time ({end})")

        # In testing or when client is unconfigured, return empty or mock bars safely
        if api_client is None:
            logger.info("Alpaca client not provided; backfill requested from %s to %s for %s", start, end, symbol)
            return []

        # Client integration (e.g. StockHistoricalDataClient or CryptoHistoricalDataClient)
        bars_result: List[MarketDataEvent] = []
        try:
            # Query client (Read-Only)
            raw_bars = api_client.get_bars(symbol=symbol, start=start, end=end, timeframe="1m")
            for r in raw_bars:
                mde = MarketDataNormalizer.normalize_raw(
                    topic="historical-backfill",
                    payload=r,
                    provenance="HISTORICAL_BACKFILL"
                )
                bars_result.append(mde)
                self.store.save_bar(mde)
        except Exception as e:
            logger.warning("Alpaca Read-Only historical fetch failed for %s: %s", symbol, e)

        return bars_result

    def load_from_fixture_file(
        self,
        filepath: str,
        symbol: Optional[str] = None,
    ) -> List[MarketDataEvent]:
        """Loads and normalizes 1m bars from a local JSON/JSONL fixture file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Fixture file not found: {filepath}")

        bars: List[MarketDataEvent] = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if symbol and record.get("symbol") != symbol:
                    continue
                # Normalize with provenance = FIXTURE
                mde = MarketDataNormalizer.normalize_raw(
                    topic="fixture-stream",
                    payload=record,
                    provenance="FIXTURE"
                )
                bars.append(mde)
        # Sort chronologically by event-time
        bars.sort(key=lambda b: b.event_time)
        return bars

    def merge_bars(
        self,
        existing_bars: List[MarketDataEvent],
        backfill_bars: List[MarketDataEvent],
    ) -> List[MarketDataEvent]:
        """
        Merges backfill bars with existing bars.
        Orders strictly by event_time and deduplicates by bar_key.
        Existing runtime bars take precedence over backfilled bars.
        """
        bar_dict: Dict[str, MarketDataEvent] = {}

        # 1. Add backfill bars first
        for b in backfill_bars:
            bar_dict[b.bar_key] = b

        # 2. Existing runtime bars overwrite backfill bars if overlap exists
        for b in existing_bars:
            bar_dict[b.bar_key] = b

        merged = list(bar_dict.values())
        merged.sort(key=lambda b: b.event_time)
        return merged

    def replay_bars(
        self,
        bars: List[MarketDataEvent],
        on_bar_callback: Callable[[MarketDataEvent], None],
    ) -> int:
        """
        Replays a sequence of bars in strict event-time order to a subscriber callback.
        Guarantees deterministic ordering.
        Returns total bars dispatched.
        """
        sorted_bars = sorted(bars, key=lambda b: (b.event_time, b.bar_revision))
        dispatched = 0
        for b in sorted_bars:
            on_bar_callback(b)
            dispatched += 1
        return dispatched

    def verify_determinism(
        self,
        bars: List[MarketDataEvent],
        process_func: Callable[[MarketDataEvent], Any],
    ) -> bool:
        """
        Executes two independent replay passes over the same bar sequence.
        Verifies that both passes generate identical result sequences (determinism check).
        """
        run1_results = []
        run2_results = []

        # Run 1
        self.replay_bars(bars, lambda b: run1_results.append(process_func(b)))

        # Run 2
        self.replay_bars(bars, lambda b: run2_results.append(process_func(b)))

        return run1_results == run2_results
