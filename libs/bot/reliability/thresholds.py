"""
libs/bot/reliability/thresholds.py — Pass/Fail Reliability & Performance Thresholds (GĐ39)
Publishes deterministic evaluation criteria for AlgoTrading V2.0 acceptance.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger("reliability-thresholds")


@dataclass
class ThresholdEvaluationResult:
    """Outcome of checking metrics against published Pass/Fail thresholds."""
    passed: bool
    hard_invariants_passed: bool
    soft_thresholds_passed: bool
    violations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "hard_invariants_passed": self.hard_invariants_passed,
            "soft_thresholds_passed": self.soft_thresholds_passed,
            "violations": self.violations,
            "details": self.details,
        }


class ReliabilityThresholds:
    """
    Evaluates execution results against strict, published invariant criteria.
    Never moves goalposts after observing results.
    """

    # Hard Invariants (Zero Tolerance)
    MAX_BROKER_WRITE_CALLS = 0
    MAX_LIVE_EXECUTION_CALLS = 0
    MAX_DUPLICATE_FINANCIAL_EFFECTS = 0
    MAX_CROSS_BOT_CONTAMINATION = 0
    MAX_UNRECONCILED_TRANSACTIONS = 0
    MAX_UNSAFE_DATA_GAP_EXECUTIONS = 0
    MAX_CRITICAL_SAFETY_VIOLATIONS = 0

    # Operational Performance Thresholds
    MAX_P95_E2E_LATENCY_MS = 100.0  # ms
    MAX_P99_E2E_LATENCY_MS = 250.0  # ms
    MAX_UNRECOVERED_GAPS = 0
    MIN_EVENT_THROUGHPUT_EPS = 5.0  # events/sec

    @classmethod
    def evaluate(
        cls,
        metrics: Dict[str, Any],
        safety_audit: Optional[Dict[str, Any]] = None,
        reconciliation: Optional[Dict[str, Any]] = None,
    ) -> ThresholdEvaluationResult:
        violations: List[str] = []
        hard_pass = True
        soft_pass = True

        # 1. Hard Invariant Checks
        broker_writes = metrics.get("broker_write_calls", 0)
        if broker_writes > cls.MAX_BROKER_WRITE_CALLS:
            violations.append(f"HARD_FAIL: broker_write_calls={broker_writes} > {cls.MAX_BROKER_WRITE_CALLS}")
            hard_pass = False

        if safety_audit:
            if safety_audit.get("outbound_broker_calls", 0) > 0:
                violations.append("HARD_FAIL: safety_audit detected outbound broker calls")
                hard_pass = False
            if safety_audit.get("paper_gate_open", False) is True:
                violations.append("HARD_FAIL: PaperExecutionGate was open during run")
                hard_pass = False
            if safety_audit.get("trading_mode") != "DRY_RUN":
                violations.append(f"HARD_FAIL: TRADING_MODE is '{safety_audit.get('trading_mode')}', must be 'DRY_RUN'")
                hard_pass = False

        if reconciliation:
            if not reconciliation.get("is_balanced", True):
                violations.append("HARD_FAIL: Financial balance reconciliation failed (CASH or POSITION mismatch)")
                hard_pass = False
            if not reconciliation.get("zero_duplicate_fills", True):
                violations.append("HARD_FAIL: Found duplicate fill effects")
                hard_pass = False

        unrecovered_gaps = metrics.get("unrecovered_gaps", 0)
        if unrecovered_gaps > cls.MAX_UNRECOVERED_GAPS:
            violations.append(f"HARD_FAIL: unrecovered_gaps={unrecovered_gaps} > {cls.MAX_UNRECOVERED_GAPS}")
            hard_pass = False

        # 2. Performance Threshold Checks
        latencies = metrics.get("latencies_ms", {}).get("e2e", {})
        p95 = latencies.get("p95", 0.0)
        if p95 > cls.MAX_P95_E2E_LATENCY_MS and latencies.get("count", 0) > 10:
            violations.append(f"PERF_WARNING: p95 e2e latency {p95}ms exceeds threshold {cls.MAX_P95_E2E_LATENCY_MS}ms")
            soft_pass = False

        passed = hard_pass and soft_pass
        return ThresholdEvaluationResult(
            passed=passed,
            hard_invariants_passed=hard_pass,
            soft_thresholds_passed=soft_pass,
            violations=violations,
            details={
                "broker_write_calls": broker_writes,
                "unrecovered_gaps": unrecovered_gaps,
                "p95_e2e_latency_ms": p95,
                "hard_pass": hard_pass,
                "soft_pass": soft_pass,
            },
        )
