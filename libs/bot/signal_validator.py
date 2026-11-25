"""
libs/bot/signal_validator.py — Signal Validation & Deduplication (GĐ31)
Enforces deterministic signal identification, deduplication across replays,
and tracks revision updates without duplicate signal emission.
"""

from typing import Dict, Any, Set, Tuple, Optional, List
import hashlib
import json
import logging

from libs.bot.domain import StrategySignal

logger = logging.getLogger("signal-validator")


class SignalValidator:
    """
    Validates, deduplicates, and manages StrategySignal lifecycle.
    Guarantees:
    1. Deterministic signal_id computed from (strategy, version, symbol, timeframe, bar_key, config_hash).
    2. Zero duplicate signals emitted across replays or redundant evaluations.
    3. Updated bar revisions trigger re-evaluations linked to parent bar revision.
    """

    def __init__(self):
        # Tracking seen deterministic IDs: signal_id -> StrategySignal
        self._seen_signals: Dict[str, StrategySignal] = {}
        # bar_key -> latest evaluated revision
        self._bar_evaluations: Dict[str, int] = {}
        self.total_evaluated = 0
        self.total_deduplicated = 0
        self.total_emitted = 0

    @staticmethod
    def compute_deterministic_signal_id(signal: StrategySignal) -> str:
        """
        Computes deterministic SHA256 signal ID:
        hash(strategy_id + strategy_version + symbol + timeframe + source_bar_key + config_hash)
        """
        seed = (
            f"{signal.strategy_id}:{signal.strategy_version}:{signal.symbol}:"
            f"{signal.timeframe}:{signal.source_bar_key}:{signal.configuration_hash}"
        )
        return f"sig_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    def validate_and_deduplicate(
        self,
        signal: StrategySignal,
    ) -> Tuple[bool, StrategySignal, str]:
        """
        Validates signal attributes and checks for duplicates.
        Returns:
            Tuple of (is_new_signal: bool, processed_signal: StrategySignal, action: str)
        """
        self.total_evaluated += 1

        # 1. Environment invariant assertion
        if signal.environment != "SIMULATION":
            raise ValueError(f"Signal security violation: environment must be 'SIMULATION', got '{signal.environment}'")

        # 2. Compute and assign deterministic signal_id
        det_id = self.compute_deterministic_signal_id(signal)
        signal.signal_id = det_id

        # 3. Check duplicate
        bar_key = signal.source_bar_key
        bar_rev = signal.source_bar_revision

        if det_id in self._seen_signals:
            existing = self._seen_signals[det_id]
            # If revision is identical, this is an exact duplicate evaluation
            if existing.source_bar_revision == bar_rev:
                self.total_deduplicated += 1
                logger.debug("Duplicate signal evaluation for %s (id: %s)", bar_key, det_id)
                return False, existing, "DUPLICATE_SUPPRESSED"

            # If incoming revision is strictly newer, update evaluation
            if bar_rev > existing.source_bar_revision:
                signal.metadata["previous_revision"] = existing.source_bar_revision
                self._seen_signals[det_id] = signal
                self._bar_evaluations[bar_key] = bar_rev
                self.total_emitted += 1
                logger.info("Signal updated for bar %s (revision %d -> %d)", bar_key, existing.source_bar_revision, bar_rev)
                return True, signal, "REVISION_UPDATED"

        # 4. Brand new signal
        self._seen_signals[det_id] = signal
        if bar_key:
            self._bar_evaluations[bar_key] = bar_rev
        self.total_emitted += 1
        return True, signal, "NEW_SIGNAL_EMITTED"

    def get_signal_by_id(self, signal_id: str) -> Optional[StrategySignal]:
        return self._seen_signals.get(signal_id)

    def get_all_signals(self) -> List[StrategySignal]:
        return list(self._seen_signals.values())
