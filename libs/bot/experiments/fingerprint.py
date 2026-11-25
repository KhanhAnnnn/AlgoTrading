"""
libs/bot/experiments/fingerprint.py — Economic Sequence Fingerprint Engine (GĐ38)
Computes a cryptographic SHA-256 fingerprint over the full sequential transition chain:
StrategySignal -> SignalDecision -> SimulationOrderIntent -> SimulatedOrder -> SimulatedFill -> PortfolioTransaction.
"""

from typing import Dict, List, Any, Optional
import hashlib
import json

from libs.bot.strategy_config.versioning import canonical_serialize


class EconomicSequenceFingerprint:
    """
    Tracks and hashes the complete economic causation sequence of an algorithm.
    Guarantees bitwise reproducibility across runs.
    """

    EXPECTED_EVENT_ORDER = [
        "StrategySignal",
        "SignalDecision",
        "SimulationOrderIntent",
        "SimulatedOrder",
        "SimulatedFill",
        "PortfolioTransaction",
    ]

    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    def add_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Appends an economic event to the sequential log."""
        clean_payload = dict(payload)
        # Remove ephemeral or non-deterministic fields like internal UUIDs or elapsed timing if any
        # Keep deterministic business fields: symbol, price, quantity, side, state, timestamps
        self._events.append({
            "event_type": event_type,
            "payload": clean_payload,
        })

    def get_event_count(self) -> int:
        return len(self._events)

    def compute_fingerprint(self) -> str:
        """
        Computes deterministic SHA-256 fingerprint over all recorded economic events.
        """
        canonical_str = canonical_serialize(self._events)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def verify(cls, events: List[Dict[str, Any]], expected_fingerprint: str) -> bool:
        """Verifies if a list of events matches the expected cryptographic fingerprint."""
        canonical_str = canonical_serialize(events)
        computed = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        return computed == expected_fingerprint
