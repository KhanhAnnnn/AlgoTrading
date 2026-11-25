"""
libs/bot/reliability/fault_injection.py — Controlled Failure Injection Engine (GĐ39)
Provides deterministic fault injection at 8 exact lifecycle interception points
without touching shared production Flink or Redpanda infrastructure.
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable, Set, List
import logging

logger = logging.getLogger("fault-injection")


class FailurePoint(str, Enum):
    """The 8 standardized failure injection points for AlgoTrading V2.0."""
    AFTER_BAR_RECEIVE = "AFTER_BAR_RECEIVE"
    AFTER_SIGNAL_GENERATE = "AFTER_SIGNAL_GENERATE"
    AFTER_INTENT_GENERATE = "AFTER_INTENT_GENERATE"
    AFTER_ORDER_CREATE = "AFTER_ORDER_CREATE"
    AFTER_FILL_SIMULATE = "AFTER_FILL_SIMULATE"
    AFTER_TRANSACTION_APPLY = "AFTER_TRANSACTION_APPLY"
    BEFORE_CHECKPOINT = "BEFORE_CHECKPOINT"
    AFTER_CHECKPOINT_BEFORE_COMMIT = "AFTER_CHECKPOINT_BEFORE_COMMIT"


class SimulatedCrashError(Exception):
    """Raised to simulate an abrupt process or subsystem crash."""
    pass


class FaultInjectionEngine:
    """
    Controlled failure injection harness.
    Can be armed to trigger on specific failure points and counts.
    """

    def __init__(self):
        # failure_point -> trigger configuration
        self._armed_points: Dict[FailurePoint, Dict[str, Any]] = {}
        self._trigger_counts: Dict[FailurePoint, int] = {p: 0 for p in FailurePoint}
        self.history: List[Dict[str, Any]] = []

    def arm(
        self,
        point: FailurePoint,
        action: str = "CRASH",  # "CRASH", "EXCEPTION", "DELAY", "DROP"
        exception_cls: Any = SimulatedCrashError,
        delay_seconds: float = 0.0,
        max_triggers: int = 1,
    ) -> None:
        """Arms a failure point."""
        self._armed_points[point] = {
            "action": action,
            "exception_cls": exception_cls,
            "delay_seconds": delay_seconds,
            "max_triggers": max_triggers,
        }
        logger.warning(f"Armed fault injection at '{point.value}' with action '{action}' (max={max_triggers})")

    def disarm(self, point: Optional[FailurePoint] = None) -> None:
        """Disarms a specific failure point or all points."""
        if point:
            self._armed_points.pop(point, None)
        else:
            self._armed_points.clear()

    def intercept(self, point: FailurePoint, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Checks if the failure point is armed and executes the configured fault.
        Returns True if a fault occurred (e.g. delay), or raises configured exception.
        """
        cfg = self._armed_points.get(point)
        if not cfg:
            return False

        if self._trigger_counts[point] >= cfg["max_triggers"]:
            return False

        self._trigger_counts[point] += 1
        record = {
            "point": point.value,
            "action": cfg["action"],
            "trigger_count": self._trigger_counts[point],
            "context": context or {},
        }
        self.history.append(record)
        logger.warning(f"Fault injection triggered at '{point.value}': action={cfg['action']}")

        action = cfg["action"]
        if action in ("CRASH", "EXCEPTION"):
            exc_cls = cfg.get("exception_cls", SimulatedCrashError)
            raise exc_cls(f"Simulated fault at {point.value}")
        elif action == "DELAY":
            import time
            time.sleep(cfg.get("delay_seconds", 0.1))
            return True
        elif action == "DROP":
            return True

        return False
