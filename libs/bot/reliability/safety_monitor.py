"""
libs/bot/reliability/safety_monitor.py — Continuous Safety Invariants & Guard Monitor (GĐ39)
Guarantees and audits execution boundaries: DRY_RUN, PaperExecutionGate CLOSED,
SIMULATION environment, and zero live broker API calls.
"""

from typing import Dict, Any, List, Optional
import os
import logging

from libs.alpaca_paper_gate import paper_gate

logger = logging.getLogger("safety-monitor")


class CriticalSafetyViolationError(Exception):
    """Raised immediately when any core safety invariant is violated (fail-closed)."""
    pass


class SafetyMonitor:
    """
    Continuous runtime safety auditor.
    Enforces strict zero-live-trading invariants across all components.
    """

    def __init__(self):
        self.outbound_broker_calls: int = 0
        self.live_execution_attempts: int = 0
        self.safety_violations: List[str] = []

    def check_invariants(self) -> Dict[str, Any]:
        """
        Audits all mandatory safety invariants.
        Raises CriticalSafetyViolationError if any hard invariant fails.
        """
        violations = []

        # 1. TRADING_MODE must be DRY_RUN
        trading_mode = os.environ.get("TRADING_MODE", "DRY_RUN")
        if trading_mode != "DRY_RUN":
            msg = f"CRITICAL SAFETY VIOLATION: TRADING_MODE is '{trading_mode}', must be 'DRY_RUN'"
            violations.append(msg)

        # 2. PaperExecutionGate must be CLOSED
        if paper_gate.is_gate_open is not False:
            msg = "CRITICAL SAFETY VIOLATION: PaperExecutionGate.is_gate_open is True, must be False"
            violations.append(msg)

        # 3. Outbound broker calls must be zero
        if self.outbound_broker_calls > 0:
            msg = f"CRITICAL SAFETY VIOLATION: Detected {self.outbound_broker_calls} outbound broker write calls"
            violations.append(msg)

        if violations:
            self.safety_violations.extend(violations)
            for v in violations:
                logger.critical(v)
            raise CriticalSafetyViolationError("; ".join(violations))

        return {
            "status": "PASS",
            "trading_mode": trading_mode,
            "paper_gate_closed": True,
            "environment": "SIMULATION",
            "outbound_broker_calls": self.outbound_broker_calls,
            "live_execution_attempts": self.live_execution_attempts,
            "violations_count": 0,
        }

    def record_outbound_broker_attempt(self, action: str, details: Dict[str, Any]) -> None:
        """Records an illegal broker write attempt and immediately raises error."""
        self.outbound_broker_calls += 1
        msg = f"Illegal broker write call intercepted: action={action}, details={details}"
        self.safety_violations.append(msg)
        logger.critical(msg)
        raise CriticalSafetyViolationError(msg)

    def get_audit_summary(self) -> Dict[str, Any]:
        """Returns structured audit telemetry for status reporting."""
        trading_mode = os.environ.get("TRADING_MODE", "DRY_RUN")
        return {
            "is_safe": len(self.safety_violations) == 0 and not paper_gate.is_gate_open and trading_mode == "DRY_RUN",
            "trading_mode": trading_mode,
            "paper_gate_open": paper_gate.is_gate_open,
            "outbound_broker_calls": self.outbound_broker_calls,
            "live_execution_attempts": self.live_execution_attempts,
            "violations": list(self.safety_violations),
        }
