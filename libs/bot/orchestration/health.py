"""
libs/bot/orchestration/health.py — Runtime Health Monitoring & Heartbeat (GĐ34)
Tracks pipeline component health, heartbeat freshness, consumer lag, and feed staleness.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger("bot-health")


class BotHealthMonitor:
    """
    Monitors operational health metrics and trips warnings upon feed staleness or latency spikes.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.lifecycle_state = "STOPPED"
        self.last_heartbeat_at = datetime.now(timezone.utc)
        self.last_event_received_at: Optional[datetime] = None
        self.last_event_processed_at: Optional[datetime] = None
        self.event_processing_latency_ms: float = 0.0
        self.consumer_health: str = "HEALTHY"
        self.strategy_engine_health: str = "HEALTHY"
        self.simulation_broker_health: str = "HEALTHY"
        self.reconciliation_status: str = "BALANCED"
        self.queue_depth: int = 0
        self.consumer_lag: int = 0
        self.events_processed_count: int = 0
        self.error_count: int = 0
        self.last_error: Optional[str] = None

    def heartbeat(self) -> None:
        """Records an operational heartbeat."""
        self.last_heartbeat_at = datetime.now(timezone.utc)

    def record_event_processed(self, latency_ms: float) -> None:
        """Updates latency and processed event count."""
        now = datetime.now(timezone.utc)
        self.last_event_processed_at = now
        self.event_processing_latency_ms = latency_ms
        self.events_processed_count += 1
        self.heartbeat()

    def record_error(self, error_message: str) -> None:
        """Records an error event."""
        self.error_count += 1
        self.last_error = error_message
        logger.warning(f"Health monitor recorded error: {error_message}")

    def check_feed_staleness(self, max_age_seconds: int = 300) -> bool:
        """
        Checks if the market data feed has gone stale.
        Returns True if stale, False if fresh.
        """
        if self.last_event_processed_at is None:
            return False  # No events processed yet

        now = datetime.now(timezone.utc)
        age = (now - self.last_event_processed_at).total_seconds()
        if age > max_age_seconds:
            self.consumer_health = "STALE_FEED"
            logger.warning(f"Market data feed is STALE: last event processed {int(age)}s ago")
            return True

        self.consumer_health = "HEALTHY"
        return False

    def get_health_status(self) -> Dict[str, Any]:
        """Returns snapshot of current operational health."""
        now = datetime.now(timezone.utc)
        hb_age = (now - self.last_heartbeat_at).total_seconds()

        return {
            "session_id": self.session_id,
            "lifecycle_state": self.lifecycle_state,
            "overall_status": "HEALTHY" if self.consumer_health == "HEALTHY" and self.error_count == 0 else "DEGRADED",
            "last_heartbeat_age_seconds": round(hb_age, 2),
            "consumer_health": self.consumer_health,
            "strategy_engine_health": self.strategy_engine_health,
            "simulation_broker_health": self.simulation_broker_health,
            "reconciliation_status": self.reconciliation_status,
            "processing_latency_ms": round(self.event_processing_latency_ms, 2),
            "queue_depth": self.queue_depth,
            "consumer_lag": self.consumer_lag,
            "events_processed_count": self.events_processed_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "environment": "SIMULATION",
        }
