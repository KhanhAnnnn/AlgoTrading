"""
libs/bot/backtesting/replay_clock.py — Virtual Simulation Clock & Deterministic Tie-Breaker (GĐ36)
Decouples simulation clock from wall-clock, guarantees deterministic ordering across multi-symbol feeds,
and evaluates event freshness relative to virtual replay time rather than real-world wall-clock time.
"""

from typing import List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import logging

from libs.bot.domain import MarketDataEvent

logger = logging.getLogger("backtest-clock")


class ReplayClock:
    """
    Virtual simulation clock that advances monotonically in lockstep with processed event time.
    Separated from real-world wall-clock time to enable replay of historical data without staleness flags.
    """

    def __init__(self, initial_time: Optional[datetime] = None):
        self._current_time: Optional[datetime] = initial_time
        self._ticks_count: int = 0

    @property
    def current_time(self) -> Optional[datetime]:
        """Returns the current virtual replay time."""
        return self._current_time

    @property
    def now(self) -> Optional[datetime]:
        """Alias for current_time."""
        return self._current_time

    @property
    def ticks_count(self) -> int:
        """Returns the total number of clock advances."""
        return self._ticks_count

    def advance_to(self, target_time: datetime) -> datetime:
        """
        Advances the virtual clock to the specified target event time.
        Enforces monotonic non-decreasing invariant.
        """
        if self._current_time is not None and target_time < self._current_time:
            raise ValueError(
                f"Clock cannot move backward: current={self._current_time.isoformat()}, target={target_time.isoformat()}"
            )
        self._current_time = target_time
        self._ticks_count += 1
        return self._current_time

    def is_stale(self, bar_time: datetime, max_staleness_seconds: float = 300.0) -> bool:
        """
        Assesses event freshness relative to the virtual replay clock (NOT wall-clock).
        Returns True if bar_time is older than max_staleness_seconds from current virtual time.
        """
        if self._current_time is None:
            return False
        age_seconds = (self._current_time - bar_time).total_seconds()
        return age_seconds > max_staleness_seconds

    @staticmethod
    def tie_break_key(bar: MarketDataEvent) -> Tuple[datetime, str, int]:
        """
        Deterministic sorting key for bars across multiple symbols:
        1. event_time (chronological order)
        2. symbol (lexicographical tie-breaker)
        3. bar_revision (revision sequence)
        """
        return (bar.event_time, bar.symbol.upper(), bar.bar_revision)

    @classmethod
    def sort_bars_deterministically(cls, bars: List[MarketDataEvent]) -> List[MarketDataEvent]:
        """
        Sorts an arbitrary list of bars into a strict deterministic replay sequence.
        Eliminates any dependency on filesystem read order or thread scheduling.
        """
        return sorted(bars, key=cls.tie_break_key)
