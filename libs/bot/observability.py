"""
libs/bot/observability.py — Data Telemetry & Latency Accounting (GĐ30)
Collects metrics on consumption rate, validation pass/fail, duplicates, revisions,
consumer lag, and explicitly breaks down Event-Time, Ingest-Time, and Processing-Time latencies.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger("data-telemetry")


class DataTelemetryCollector:
    """
    Central telemetry collector for V2 Market Data Ingestion.
    Maintains counters and latency percentiles without confounding internal processing
    latency with external market data freshness.
    """

    def __init__(self):
        # Operational counters
        self.messages_consumed: int = 0
        self.valid_bars: int = 0
        self.invalid_bars: int = 0
        self.duplicates: int = 0
        self.revisions: int = 0
        self.late_events: int = 0
        self.missing_intervals: int = 0
        self.stale_events: int = 0

        # Latency accumulators (milliseconds)
        self._consume_latencies_ms = []
        self._norm_latencies_ms = []
        self._source_to_consume_latencies_ms = []

        # Consumer partition lags: topic:partition -> lag
        self.consumer_lags: Dict[str, int] = {}
        self.start_time = datetime.now(timezone.utc)

    def record_message(
        self,
        event_time: datetime,
        ingest_time: datetime,
        processing_time: datetime,
        is_valid: bool = True,
        is_duplicate: bool = False,
        is_revision: bool = False,
        is_late: bool = False,
        is_missing_interval: bool = False,
        is_stale: bool = False,
        normalization_duration_ms: float = 0.5,
    ) -> None:
        """
        Records a single processed bar with complete temporal breakdown:
        - Event-Time: trade occurrence
        - Ingest-Time: arrival at streaming transport (Redpanda)
        - Processing-Time: arrival at normalizer
        """
        self.messages_consumed += 1

        if is_valid:
            self.valid_bars += 1
        else:
            self.invalid_bars += 1

        if is_duplicate:
            self.duplicates += 1
        if is_revision:
            self.revisions += 1
        if is_late:
            self.late_events += 1
        if is_missing_interval:
            self.missing_intervals += 1
        if is_stale:
            self.stale_events += 1

        # 1. Consume Latency: Processing-Time minus Ingest-Time
        consume_lat = max(0.0, (processing_time - ingest_time).total_seconds() * 1000.0)
        self._consume_latencies_ms.append(consume_lat)

        # 2. Source-to-Consume Latency: Processing-Time minus Event-Time
        source_lat = max(0.0, (processing_time - event_time).total_seconds() * 1000.0)
        self._source_to_consume_latencies_ms.append(source_lat)

        # 3. Normalization Latency
        self._norm_latencies_ms.append(normalization_duration_ms)

        # Keep sliding buffer size bounded
        if len(self._consume_latencies_ms) > 10000:
            self._consume_latencies_ms = self._consume_latencies_ms[-5000:]
            self._source_to_consume_latencies_ms = self._source_to_consume_latencies_ms[-5000:]
            self._norm_latencies_ms = self._norm_latencies_ms[-5000:]

    def record_lag(self, topic: str, partition: int, lag: int) -> None:
        """Records current consumer offset lag."""
        key = f"{topic}:{partition}"
        self.consumer_lags[key] = max(0, lag)

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot of ingestion telemetry."""
        avg_consume_lat = (
            sum(self._consume_latencies_ms) / len(self._consume_latencies_ms)
            if self._consume_latencies_ms
            else 0.0
        )
        avg_norm_lat = (
            sum(self._norm_latencies_ms) / len(self._norm_latencies_ms)
            if self._norm_latencies_ms
            else 0.0
        )
        avg_source_lat = (
            sum(self._source_to_consume_latencies_ms) / len(self._source_to_consume_latencies_ms)
            if self._source_to_consume_latencies_ms
            else 0.0
        )

        total_lag = sum(self.consumer_lags.values())

        return {
            "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "messages_consumed": self.messages_consumed,
            "valid_bars": self.valid_bars,
            "invalid_bars": self.invalid_bars,
            "duplicates": self.duplicates,
            "revisions": self.revisions,
            "late_events": self.late_events,
            "missing_intervals": self.missing_intervals,
            "stale_events": self.stale_events,
            "total_consumer_lag": total_lag,
            "consumer_lags_by_partition": dict(self.consumer_lags),
            "latency_metrics": {
                "avg_consume_latency_ms": round(avg_consume_lat, 2),
                "avg_normalization_latency_ms": round(avg_norm_lat, 2),
                "avg_source_to_consume_latency_ms": round(avg_source_lat, 2),
                "latency_definitions": {
                    "consume_latency": "processing_time - ingest_time",
                    "normalization_latency": "cpu time normalizing payload to MarketDataEvent",
                    "source_to_consume_latency": "processing_time - event_time (includes market feed latency)",
                },
            },
        }

    def export_summary(self, filepath: str) -> None:
        """Exports snapshot to a JSON file."""
        snapshot = self.get_telemetry_snapshot()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
