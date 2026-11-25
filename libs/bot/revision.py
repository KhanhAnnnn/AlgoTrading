"""
libs/bot/revision.py — Bar Finalization & Revision Management (GĐ30)
Enforces unique bar_key (symbol + timeframe + event_time), tracks bar revisions,
applies final_only forwarding policies, and handles out-of-order bar updates deterministically.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
import logging
import copy

from libs.bot.domain import MarketDataEvent, BotAuditEvent

logger = logging.getLogger("bar-revision-manager")


class BarRevisionManager:
    """
    Tracks and manages 1-minute bar lifecycle, revisions, and finalization status.
    Guarantees:
    1. A bar_key has exactly one active representation in the active cache.
    2. Updates increment revision number rather than creating duplicate independent bars.
    3. Full revision history is preserved for audit and replay.
    4. Provisional bars (is_final=False) are suppressed from strategy generation when final_only=True.
    5. Finalized bars (is_final=True) supersede provisional bars.
    """

    def __init__(self, final_only: bool = True):
        self.final_only = final_only
        # bar_key -> current active MarketDataEvent
        self._active_bars: Dict[str, MarketDataEvent] = {}
        # bar_key -> list of all revision historical snapshots
        self._revision_history: Dict[str, List[MarketDataEvent]] = {}
        # Audit log of revision events
        self._revision_audit: List[Dict[str, Any]] = []

    def get_bar_key(self, bar: MarketDataEvent) -> str:
        return bar.bar_key

    def get_active_bar(self, bar_key: str) -> Optional[MarketDataEvent]:
        return self._active_bars.get(bar_key)

    def get_revision_history(self, bar_key: str) -> List[MarketDataEvent]:
        return list(self._revision_history.get(bar_key, []))

    def process_incoming_bar(
        self,
        bar: MarketDataEvent,
    ) -> Tuple[Optional[MarketDataEvent], str]:
        """
        Processes an incoming normalized MarketDataEvent.
        Returns:
            Tuple of (forwardable_bar_or_none, action_verdict)
        """
        key = self.get_bar_key(bar)

        if key not in self._active_bars:
            # Case 1: First observation of this bar_key
            bar.bar_revision = 0
            self._active_bars[key] = bar
            self._revision_history[key] = [copy.deepcopy(bar)]

            if not bar.is_final:
                if self.final_only:
                    logger.debug("Bar %s received as PROVISIONAL (revision 0). Stored, not forwarded.", key)
                    return None, "PROVISIONAL_STORED"
                return bar, "PROVISIONAL_FORWARDED"

            logger.debug("Bar %s received as FINAL (revision 0). Forwarded.", key)
            return bar, "NEW_FINAL_FORWARDED"

        # Case 2: Bar already exists -> Update revision
        existing = self._active_bars[key]

        # Check out-of-order: if existing was already final and incoming is provisional,
        # ignore or flag as out-of-order late provisional update
        if existing.is_final and not bar.is_final:
            logger.warning(
                "Out-of-order anomaly on %s: incoming is provisional after bar was finalized. Keeping finalized version.",
                key
            )
            self._revision_audit.append({
                "bar_key": key,
                "event": "OUT_OF_ORDER_PROVISIONAL_IGNORED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "existing_revision": existing.bar_revision,
            })
            return None, "OUT_OF_ORDER_PROVISIONAL_IGNORED"

        # Increment revision counter
        new_revision = existing.bar_revision + 1
        bar.bar_revision = new_revision

        # Update active state and append to revision trail
        self._active_bars[key] = bar
        self._revision_history[key].append(copy.deepcopy(bar))

        self._revision_audit.append({
            "bar_key": key,
            "event": "REVISION_UPDATED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_revision": new_revision,
            "is_final": bar.is_final,
        })

        if self.final_only:
            if bar.is_final:
                logger.info("Bar %s updated to FINAL at revision %d. Forwarded.", key, new_revision)
                return bar, "FINAL_REVISION_FORWARDED"
            logger.debug("Bar %s updated at revision %d (still provisional). Stored, not forwarded.", key, new_revision)
            return None, "PROVISIONAL_REVISION_STORED"

        # If policy is not final_only, forward every revision
        return bar, "REVISION_FORWARDED"

    def get_all_active_bars(self) -> Dict[str, MarketDataEvent]:
        return dict(self._active_bars)

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return list(self._revision_audit)
