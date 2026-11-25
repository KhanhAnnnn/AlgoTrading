"""
libs/shadow_mode_observer.py — GĐ17 Shadow Mode Signal Observer & Forward Validation Engine
Provides read-only observation, deduplication, latency tracking, and deterministic recording
of trading signals and non-signal market events with ZERO order execution authority.
"""

import os
import sys
import time
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

for d in [DATA_DIR, STATUS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

SHADOW_LOG_FILE = os.path.join(STATUS_DIR, 'shadow_observations.jsonl')
SHADOW_METRICS_FILE = os.path.join(STATUS_DIR, 'shadow_metrics.json')

logger = logging.getLogger('shadow-observer')


class ShadowSignalObserver:
    """
    Shadow Mode Signal Observer.
    Strictly read-only: observes signals and non-signal evaluations from stream.
    Zero execution capability: all observations are tagged 'OBSERVED_ONLY_NO_ORDER'.
    """

    STRATEGY_ID = "Strategy_1_PDF_Baseline"
    STRATEGY_VERSION = "1.0.0"

    # Configurable SLA Thresholds (seconds/ms)
    CRYPTO_FRESHNESS_MAX_AGE_SEC = 300.0  # 24/7 continuous stream SLA
    STOCKS_FRESHNESS_MAX_AGE_SEC = 180.0  # During regular market hours
    MAX_PERMISSIBLE_CONSUMER_LAG = 50     # Max tolerable unconsumed records
    MAX_PIPELINE_LATENCY_MS = 10000.0     # 10s max source-to-observer latency

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or SHADOW_LOG_FILE
        self.seen_event_ids = set()
        self._load_existing_index()

    def _load_existing_index(self):
        """Load previously recorded event IDs for stateful deduplication across restarts."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                record = json.loads(line)
                                eid = record.get('event_id')
                                if eid:
                                    self.seen_event_ids.add(eid)
                            except Exception:
                                continue
            except Exception as e:
                logger.warning("Error indexing existing shadow log: %s", e)

    @staticmethod
    def generate_event_id(symbol: str, event_time_str: str, signal_type: str, is_fixture: bool = False) -> str:
        """Deterministic sanitized hash ID based on event attributes."""
        salt = "FIXTURE:" if is_fixture else "NATURAL:"
        raw = f"{salt}{symbol}:{event_time_str}:{signal_type}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def normalize_symbol(symbol: str) -> Tuple[str, str]:
        """
        Normalize symbol and determine asset class.
        Stocks: NVDA, AAPL -> 'stocks'
        Crypto: BTC/USD, ETH/USD, BTCUSD -> 'crypto' (normalized to BTC/USD)
        """
        sym = symbol.strip().upper()
        if sym in ('BTCUSD', 'BTC/USD'):
            return 'BTC/USD', 'crypto'
        if sym in ('ETHUSD', 'ETH/USD'):
            return 'ETH/USD', 'crypto'
        if '/' in sym:
            return sym, 'crypto'
        return sym, 'stocks'

    def record_observation(
        self,
        symbol: str,
        signal_type: str,
        event_time: Union[str, datetime, float, int],
        ingest_time: Optional[Union[str, datetime, float, int]] = None,
        price: Optional[float] = None,
        sentiment: Optional[float] = None,
        sma_20: Optional[float] = None,
        sma_50: Optional[float] = None,
        no_signal_reason: str = "NONE",
        input_data_state: str = "VALID",
        is_fixture: bool = False,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record a shadow observation with full provenance and latency calculations.
        """
        now = datetime.now(timezone.utc)
        processing_time_iso = now.isoformat()

        # Normalize symbol & asset class
        norm_symbol, asset_class = self.normalize_symbol(symbol)

        # Format event_time ISO
        if isinstance(event_time, (int, float)):
            dt_event = datetime.fromtimestamp(event_time / 1000.0 if event_time > 1e11 else event_time, tz=timezone.utc)
            event_time_iso = dt_event.isoformat()
        elif isinstance(event_time, datetime):
            dt_event = event_time if event_time.tzinfo else event_time.replace(tzinfo=timezone.utc)
            event_time_iso = dt_event.isoformat()
        else:
            event_time_iso = str(event_time)
            try:
                dt_event = datetime.fromisoformat(event_time_iso.replace('Z', '+00:00'))
            except Exception:
                dt_event = now

        # Format ingest_time ISO
        if ingest_time is None:
            dt_ingest = now
            ingest_time_iso = processing_time_iso
        elif isinstance(ingest_time, (int, float)):
            dt_ingest = datetime.fromtimestamp(ingest_time / 1000.0 if ingest_time > 1e11 else ingest_time, tz=timezone.utc)
            ingest_time_iso = dt_ingest.isoformat()
        elif isinstance(ingest_time, datetime):
            dt_ingest = ingest_time if ingest_time.tzinfo else ingest_time.replace(tzinfo=timezone.utc)
            ingest_time_iso = dt_ingest.isoformat()
        else:
            ingest_time_iso = str(ingest_time)
            try:
                dt_ingest = datetime.fromisoformat(ingest_time_iso.replace('Z', '+00:00'))
            except Exception:
                dt_ingest = now

        # Latency computations
        source_to_ingest_ms = round((dt_ingest - dt_event).total_seconds() * 1000.0, 2)
        ingest_to_process_ms = round((now - dt_ingest).total_seconds() * 1000.0, 2)
        total_pipeline_latency_ms = round(source_to_ingest_ms + ingest_to_process_ms, 2)

        # Generate deterministic event_id
        event_id = self.generate_event_id(norm_symbol, event_time_iso, signal_type, is_fixture=is_fixture)

        # Deduplication check
        if event_id in self.seen_event_ids:
            dedup_state = "DUPLICATE_SKIPPED"
        else:
            dedup_state = "NEW_OBSERVATION"
            self.seen_event_ids.add(event_id)

        # Check latency SLA
        if total_pipeline_latency_ms > self.MAX_PIPELINE_LATENCY_MS:
            if input_data_state == "VALID":
                input_data_state = "DELAYED"

        # Observation record structure (ZERO credentials, ZERO order actions)
        record = {
            "event_id": event_id,
            "symbol": norm_symbol,
            "asset_class": asset_class,
            "strategy_id": self.STRATEGY_ID,
            "strategy_version": self.STRATEGY_VERSION,
            "event_time": event_time_iso,
            "ingest_time": ingest_time_iso,
            "processing_time": processing_time_iso,
            "source_to_ingest_ms": source_to_ingest_ms,
            "ingest_to_process_ms": ingest_to_process_ms,
            "total_pipeline_latency_ms": total_pipeline_latency_ms,
            "signal_type": signal_type.upper(),
            "no_signal_reason": no_signal_reason,
            "price": price,
            "sentiment": sentiment,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "input_data_state": input_data_state,
            "dedup_state": dedup_state,
            "is_fixture": bool(is_fixture),
            "execution_intent": "OBSERVED_ONLY_NO_ORDER",
            "observation_verdict": "RECORDED" if dedup_state == "NEW_OBSERVATION" else "IGNORED_DUPLICATE",
        }

        # Append to persistent JSONL log
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + '\n')
        except Exception as e:
            logger.error("Failed to append to shadow observations log: %s", e)

        return record

    def get_metrics(self) -> Dict[str, Any]:
        """Compute aggregated forward validation metrics across all observed records."""
        total_records = 0
        new_observations = 0
        duplicates = 0
        fixtures = 0
        natural_events = 0
        signals_by_type = {"BUY": 0, "SELL": 0, "NO_SIGNAL": 0}
        signals_by_symbol = {}
        latencies = []
        data_states = {"VALID": 0, "DELAYED": 0, "MISSING_DATA": 0, "ERROR": 0}

        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        r = json.loads(line)
                        total_records += 1
                        if r.get("dedup_state") == "NEW_OBSERVATION":
                            new_observations += 1
                            sig = r.get("signal_type", "NO_SIGNAL")
                            signals_by_type[sig] = signals_by_type.get(sig, 0) + 1
                            sym = r.get("symbol", "UNKNOWN")
                            signals_by_symbol[sym] = signals_by_symbol.get(sym, 0) + 1
                            if r.get("is_fixture"):
                                fixtures += 1
                            else:
                                natural_events += 1
                            lat = r.get("total_pipeline_latency_ms")
                            if lat is not None and lat >= 0:
                                latencies.append(lat)
                            st = r.get("input_data_state", "VALID")
                            data_states[st] = data_states.get(st, 0) + 1
                        else:
                            duplicates += 1
            except Exception as e:
                logger.error("Error reading shadow log for metrics: %s", e)

        latencies.sort()
        count_lat = len(latencies)
        p50 = latencies[int(count_lat * 0.5)] if count_lat > 0 else 0.0
        p95 = latencies[int(count_lat * 0.95)] if count_lat > 0 else 0.0
        mean_lat = round(sum(latencies) / count_lat, 2) if count_lat > 0 else 0.0

        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_records_processed": total_records,
            "unique_observations": new_observations,
            "duplicates_suppressed": duplicates,
            "natural_market_events": natural_events,
            "fixture_events": fixtures,
            "signals_by_type": signals_by_type,
            "signals_by_symbol": signals_by_symbol,
            "input_data_states": data_states,
            "latency_ms": {
                "mean": mean_lat,
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "max": round(latencies[-1], 2) if count_lat > 0 else 0.0,
            },
            "sla_compliance": {
                "max_pipeline_latency_ms": self.MAX_PIPELINE_LATENCY_MS,
                "latency_within_sla": p95 <= self.MAX_PIPELINE_LATENCY_MS if count_lat > 0 else True,
                "order_execution_count": 0,
                "trading_mode": "DRY_RUN",
                "shadow_mode_active": True,
            }
        }

        # Persist metrics summary
        try:
            with open(SHADOW_METRICS_FILE, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save shadow metrics: %s", e)

        return metrics

    def get_recent_observations(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent shadow observations."""
        records = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        if not line.strip():
                            continue
                        r = json.loads(line)
                        if symbol and r.get("symbol") != symbol:
                            continue
                        records.append(r)
                        if len(records) >= limit:
                            break
            except Exception as e:
                logger.error("Error retrieving recent observations: %s", e)
        return records


# Global singleton instance
shadow_observer = ShadowSignalObserver()

