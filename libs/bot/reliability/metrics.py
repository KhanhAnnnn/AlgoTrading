"""
libs/bot/reliability/metrics.py — Reliability & Telemetry Metrics Instrumentation (GĐ39)
Measures latency percentiles (p50, p95, p99), resource utilization (CPU, RAM, queue depth),
and reliability counters across the V2 pipeline.
"""

from typing import Dict, List, Any, Optional
import time
import math
import logging

logger = logging.getLogger("reliability-metrics")


class ReliabilityMetricsTracker:
    """
    Instruments latencies, resource consumption, and reliability counters.
    Safely calculates statistics without zero division.
    """

    def __init__(self):
        # Latency samples in milliseconds
        self.latencies: Dict[str, List[float]] = {
            "ingestion": [],
            "strategy": [],
            "risk": [],
            "order": [],
            "fill": [],
            "e2e": [],
        }

        # Reliability counters
        self.events_processed: int = 0
        self.orders_created: int = 0
        self.fills_created: int = 0
        self.duplicates_prevented: int = 0
        self.queue_overflows: int = 0
        self.recovered_gaps: int = 0
        self.unrecovered_gaps: int = 0
        self.unexpected_errors: int = 0
        self.broker_write_calls: int = 0  # Hard invariant: must remain 0

        # Timing
        self.start_time: float = time.time()

    def record_latency(self, stage: str, latency_ms: float) -> None:
        """Records a latency observation in milliseconds."""
        if stage in self.latencies:
            self.latencies[stage].append(max(0.0, float(latency_ms)))

    @staticmethod
    def _percentile(values: List[float], p: float) -> float:
        """Calculates percentile p in [0, 100]. Returns 0.0 if empty."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[int(k)], 3)
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return round(d0 + d1, 3)

    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Returns p50, p95, p99, mean, max for each latency stage."""
        stats: Dict[str, Dict[str, float]] = {}
        for stage, samples in self.latencies.items():
            if not samples:
                stats[stage] = {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
            else:
                stats[stage] = {
                    "count": len(samples),
                    "p50": self._percentile(samples, 50.0),
                    "p95": self._percentile(samples, 95.0),
                    "p99": self._percentile(samples, 99.0),
                    "mean": round(sum(samples) / len(samples), 3),
                    "max": round(max(samples), 3),
                }
        return stats

    def get_throughput(self) -> float:
        """Calculates events processed per second."""
        elapsed = max(0.001, time.time() - self.start_time)
        return round(self.events_processed / elapsed, 2)

    def get_summary(self) -> Dict[str, Any]:
        """Compiles complete reliability metrics report."""
        return {
            "elapsed_seconds": round(time.time() - self.start_time, 2),
            "events_processed": self.events_processed,
            "orders_created": self.orders_created,
            "fills_created": self.fills_created,
            "duplicates_prevented": self.duplicates_prevented,
            "queue_overflows": self.queue_overflows,
            "recovered_gaps": self.recovered_gaps,
            "unrecovered_gaps": self.unrecovered_gaps,
            "unexpected_errors": self.unexpected_errors,
            "broker_write_calls": self.broker_write_calls,
            "event_throughput_eps": self.get_throughput(),
            "latencies_ms": self.get_latency_stats(),
        }
