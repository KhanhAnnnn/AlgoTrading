"""
libs/bot/backtesting/replay_controller.py — Historical Replay Controller (GĐ36)
Executes deterministic bar-by-bar playback in FAST, PACED, or STEP modes.
Supports pause, resume, cancel, step-through, and progress telemetry hooks.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
import time
import logging

from libs.bot.domain import MarketDataEvent
from libs.bot.backtesting.replay_clock import ReplayClock

logger = logging.getLogger("replay-controller")


class ReplayMode(str, Enum):
    FAST_REPLAY = "FAST_REPLAY"
    PACED_REPLAY = "PACED_REPLAY"
    STEP_REPLAY = "STEP_REPLAY"


class ReplayState(str, Enum):
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class ReplayController:
    """
    Controls execution flow of historical bar playback to simulated consumers.
    Guarantees strict event-time progression without look-ahead bias.
    """

    def __init__(
        self,
        bars: List[MarketDataEvent],
        mode: ReplayMode = ReplayMode.FAST_REPLAY,
        pace_delay_seconds: float = 0.001,
        on_bar_callback: Optional[Callable[[MarketDataEvent, ReplayClock], None]] = None,
        on_progress_callback: Optional[Callable[[int, int, Optional[datetime]], None]] = None,
    ):
        # Sort bars strictly using deterministic tie-breaker
        self._bars = ReplayClock.sort_bars_deterministically(bars)
        self.mode = mode
        self.pace_delay_seconds = pace_delay_seconds
        self.on_bar_callback = on_bar_callback
        self.on_progress_callback = on_progress_callback

        self.clock = ReplayClock()
        self.state = ReplayState.INITIALIZED
        self._current_index = 0
        self._is_cancelled = False

    @property
    def total_bars(self) -> int:
        return len(self._bars)

    @property
    def processed_bars(self) -> int:
        return self._current_index

    @property
    def processed_count(self) -> int:
        """Alias for processed_bars."""
        return self._current_index

    @property
    def progress_pct(self) -> float:
        if not self._bars:
            return 100.0
        return (self._current_index / len(self._bars)) * 100.0

    def pause(self) -> bool:
        """Pauses playback."""
        if self.state in (ReplayState.RUNNING, ReplayState.INITIALIZED):
            self.state = ReplayState.PAUSED
            logger.info("ReplayController PAUSED")
            return True
        return False

    def resume(self) -> bool:
        """Resumes paused playback."""
        if self.state == ReplayState.PAUSED:
            self.state = ReplayState.RUNNING
            logger.info("ReplayController RESUMED")
            return True
        return False

    def cancel(self) -> bool:
        """Cancels playback."""
        self._is_cancelled = True
        self.state = ReplayState.CANCELLED
        logger.info("ReplayController CANCELLED")
        return True

    def step(self) -> Optional[MarketDataEvent]:
        """
        Executes exactly one bar in STEP mode or when manual stepping is invoked.
        Advances replay clock and invokes callback.
        """
        if self._is_cancelled or self._current_index >= len(self._bars):
            if self._current_index >= len(self._bars) and not self._is_cancelled:
                self.state = ReplayState.COMPLETED
            return None

        bar = self._bars[self._current_index]
        self.clock.advance_to(bar.event_time)

        if self.on_bar_callback:
            self.on_bar_callback(bar, self.clock)

        self._current_index += 1

        if self.on_progress_callback:
            self.on_progress_callback(self._current_index, len(self._bars), self.clock.current_time)

        if self._current_index >= len(self._bars):
            self.state = ReplayState.COMPLETED

        return bar

    def run(self) -> int:
        """
        Runs replay until completion, pause, or cancellation.
        Returns total number of bars processed during this run invocation.
        """
        self.state = ReplayState.RUNNING
        processed_this_run = 0

        while self._current_index < len(self._bars):
            if self._is_cancelled:
                self.state = ReplayState.CANCELLED
                break

            if self.state == ReplayState.PAUSED:
                break

            if self.mode == ReplayMode.STEP_REPLAY:
                # Step mode: process one bar and return control
                self.step()
                processed_this_run += 1
                break

            # Process bar
            self.step()
            processed_this_run += 1

            if self.mode == ReplayMode.PACED_REPLAY and self.pace_delay_seconds > 0:
                time.sleep(self.pace_delay_seconds)

        if self._current_index >= len(self._bars) and not self._is_cancelled:
            self.state = ReplayState.COMPLETED

        return processed_this_run

    def start(self) -> int:
        """Alias for run()."""
        return self.run()
