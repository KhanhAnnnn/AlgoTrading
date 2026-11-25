"""
reliability_service.py — Self-Healing, Deduplication, and Slack Outbox Telemetry Service (GĐ15.1)
Inspects recovery reports, stateful deduplication indices, dead-letter queues,
and parses append-only Slack Outbox logs into distinct event states, transition histories,
and segregates test fixtures from live production events.
"""
import os
import json
import time
from typing import Dict, Any, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
ORDERS_DIR = os.path.join(DATA_DIR, 'orders')

RECOVERY_REPORT_FILE = os.path.join(STATUS_DIR, 'recovery_report.json')
SLACK_OUTBOX_FILE = os.path.join(STATUS_DIR, 'slack_outbox.jsonl')
SLACK_DEAD_LETTER_FILE = os.path.join(STATUS_DIR, 'slack_dead_letter.jsonl')
DEDUP_SIGNALS_FILE = os.path.join(ORDERS_DIR, 'stocks_processed_signals.json')


def _sanitize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Strips sensitive webhook URLs or authorization tokens if present."""
    sanitized = dict(rec)
    for sensitive_key in ('token', 'webhook_url', 'auth', 'secret', 'key'):
        if sensitive_key in sanitized:
            sanitized[sensitive_key] = '[REDACTED]'
    return sanitized


def get_reliability_telemetry() -> Dict[str, Any]:
    """Returns reliability metrics and event logs for the dashboard with state transition reduction."""
    # 1. Recovery Report
    recovery_data = {
        "status": "IDLE",
        "timestamp": None,
        "actions_taken": [],
        "total_actions": 0
    }
    if os.path.exists(RECOVERY_REPORT_FILE):
        try:
            with open(RECOVERY_REPORT_FILE, 'r', encoding='utf-8-sig') as f:
                r_json = json.load(f)
                recovery_data["status"] = r_json.get("status", "SUCCESS")
                recovery_data["timestamp"] = r_json.get("timestamp")
                recovery_data["actions_taken"] = r_json.get("actions_taken", [])
                recovery_data["total_actions"] = len(recovery_data["actions_taken"])
        except Exception:
            pass

    # 2. Slack Outbox State Reduction (Append-only Log -> Current Event State)
    events_map: Dict[str, List[Dict[str, Any]]] = {}
    raw_lines_count = 0

    if os.path.exists(SLACK_OUTBOX_FILE):
        try:
            with open(SLACK_OUTBOX_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_lines_count += 1
                        rec = json.loads(line)
                        sig_id = rec.get("signal_id") or rec.get("dedup_key") or f"evt-{raw_lines_count}"
                        if sig_id not in events_map:
                            events_map[sig_id] = []
                        events_map[sig_id].append(_sanitize_record(rec))
        except Exception:
            pass

    # Compile unique event states
    outbox_events = []
    outbox_summary = {
        "raw_transitions_total": raw_lines_count,
        "unique_events_total": len(events_map),
        "pending": 0,
        "delivered": 0,
        "failed": 0,
        "test_fixtures_count": 0,
        "production_events_count": 0
    }

    for sig_id, attempts in events_map.items():
        latest_attempt = attempts[-1]
        current_status = latest_attempt.get("status", "UNKNOWN")
        is_test = "TEST" in sig_id.upper() or "TEST" in str(latest_attempt.get("dedup_key", "")).upper()

        if is_test:
            outbox_summary["test_fixtures_count"] += 1
        else:
            outbox_summary["production_events_count"] += 1

        if current_status == "PENDING":
            outbox_summary["pending"] += 1
        elif current_status == "DELIVERED":
            outbox_summary["delivered"] += 1
        elif current_status in ("FAILED", "FAILED_TRANSIENT", "DLQ"):
            outbox_summary["failed"] += 1

        outbox_events.append({
            "signal_id": sig_id,
            "dedup_key": latest_attempt.get("dedup_key"),
            "current_status": current_status,
            "is_test_fixture": is_test,
            "latest_timestamp": latest_attempt.get("timestamp"),
            "latest_iso_time": latest_attempt.get("iso_time"),
            "slack_ts": latest_attempt.get("slack_ts"),
            "attempt_count": len(attempts),
            "attempt_history": attempts
        })

    # Sort descending by latest_timestamp
    outbox_events.sort(key=lambda x: x.get("latest_timestamp") or 0, reverse=True)

    # 3. Slack Dead Letter Queue
    dlq_records = []
    if os.path.exists(SLACK_DEAD_LETTER_FILE):
        try:
            with open(SLACK_DEAD_LETTER_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        is_test = "TEST" in str(rec.get("signal_id", "")).upper()
                        s_rec = _sanitize_record(rec)
                        s_rec["is_test_fixture"] = is_test
                        dlq_records.append(s_rec)
        except Exception:
            pass

    # 4. Processed Signals (Deduplication Log)
    dedup_keys = []
    if os.path.exists(DEDUP_SIGNALS_FILE):
        try:
            with open(DEDUP_SIGNALS_FILE, 'r', encoding='utf-8') as f:
                dedup_keys = json.load(f)
        except Exception:
            pass

    return {
        "timestamp": int(time.time()),
        "recovery": recovery_data,
        "outbox": {
            "summary": outbox_summary,
            "events": outbox_events,
            "count": len(outbox_events)
        },
        "dead_letter_queue": {
            "count": len(dlq_records),
            "records": dlq_records
        },
        "deduplication": {
            "total_keys": len(dedup_keys),
            "keys": dedup_keys[-50:]
        }
    }
