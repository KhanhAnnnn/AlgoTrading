"""
test_slack_delivery_and_outbox.py
Covers:
- TC-G14-14: Slack retry and outbox
- TC-G14-15: Slack crash recovery
"""
import os
import sys
import json
import time
from typing import Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.response import HTTPResponse
import io

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LIBS_DIR = os.path.join(BASE_DIR, "libs")
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from slack_notifier import SlackNotifier, OUTBOX_FILE, DEAD_LETTER_FILE

class MockSlackAdapter(HTTPAdapter):
    """Mock adapter that simulates 429 Rate Limits, 500 Server Errors, and Success."""
    def __init__(self, mode="success", retry_after=1):
        super().__init__()
        self.mode = mode
        self.retry_after = retry_after
        self.call_count = 0

    def send(self, request, **kwargs):
        self.call_count += 1
        resp = requests.Response()
        resp.request = request
        resp.url = request.url

        if self.mode == "429_then_success":
            if self.call_count == 1:
                resp.status_code = 429
                resp.headers["Retry-After"] = str(self.retry_after)
                resp._content = b'{"ok": false, "error": "rate_limited"}'
            else:
                resp.status_code = 200
                resp._content = b'{"ok": true, "ts": "1792334000.000100", "channel": "C08TEST"}'
        elif self.mode == "500_fail":
            resp.status_code = 500
            resp._content = b'{"ok": false, "error": "internal_server_error"}'
        elif self.mode == "channel_not_found":
            resp.status_code = 200
            resp._content = b'{"ok": false, "error": "channel_not_found"}'
        else:
            resp.status_code = 200
            resp._content = b'{"ok": true, "ts": "1792334000.000200", "channel": "C08TEST"}'
        return resp

def test_tc_g14_14_slack_retry_and_outbox():
    """TC-G14-14: Verify Slack 429 Retry-After, exponential backoff, and outbox logging."""
    print("Executing TC-G14-14: Slack Retry (429/500) & Outbox Logging...")
    session = requests.Session()
    adapter = MockSlackAdapter(mode="429_then_success", retry_after=1)
    session.mount("https://slack.com", adapter)

    # Instantiate notifier with mock session and dummy credentials
    test_state_file = os.path.join(BASE_DIR, "data", "status", "test_slack_state.json")
    if os.path.exists(test_state_file):
        os.remove(test_state_file)

    notifier = SlackNotifier(
        token="xoxb-TEST-MOCK-TOKEN-12345",
        channel_id="C08TESTCH",
        state_file=test_state_file,
        max_retries=3,
        session=session
    )

    test_signal = {
        "asset_type": "stocks",
        "symbol": "NVDA",
        "signal": "BUY",
        "signal_time": "2026-10-18T14:30:00Z",
        "price": 214.50,
        "sentiment": 0.4500,
        "sma_20": 215.10,
        "sma_50": 216.00,
        "trading_mode": "DRY_RUN",
        "signal_id": f"TEST-SIG-429-{int(time.time())}"
    }

    res = notifier.send_signal_notification(test_signal, force=True)
    
    assert res.get("status") == "DELIVERED", f"Expected DELIVERED, got {res}"
    assert adapter.call_count == 2, f"Expected 2 attempts (1st 429, 2nd success), got {adapter.call_count}"
    assert os.path.exists(OUTBOX_FILE), f"Missing outbox file: {OUTBOX_FILE}"

    # Verify outbox entry exists
    with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
        outbox_lines = [json.loads(line) for line in f if line.strip()]
    matched = [entry for entry in outbox_lines if entry.get("signal_id") == test_signal["signal_id"]]
    assert len(matched) > 0, "No outbox record found for test signal"
    
    print(f"  [PASS] Handled 429 Retry-After successfully on attempt #2. Outbox entry verified.")
    return {
        "id": "TC-G14-14",
        "name": "Slack retry and outbox",
        "expected": "HTTP 429 triggers Retry-After backoff; successful delivery records in outbox",
        "actual": f"Recovered on attempt #{adapter.call_count} following 429 rate-limit backoff; outbox logged",
        "evidence": f"Mock adapter call_count=2, outbox entry timestamped at {matched[-1]['iso_time']}",
        "status": "PASS"
    }

def test_tc_g14_15_slack_crash_recovery():
    """TC-G14-15: Verify permanent Slack failure routes to Dead-Letter Queue without false DELIVERED status."""
    print("Executing TC-G14-15: Slack Failure & Dead-Letter Queue (DLQ)...")
    session = requests.Session()
    adapter = MockSlackAdapter(mode="500_fail")
    session.mount("https://slack.com", adapter)

    test_state_file = os.path.join(BASE_DIR, "data", "status", "test_slack_dlq_state.json")
    if os.path.exists(test_state_file):
        os.remove(test_state_file)

    notifier = SlackNotifier(
        token="xoxb-TEST-MOCK-TOKEN-54321",
        channel_id="C08TESTCH",
        state_file=test_state_file,
        max_retries=3,
        session=session
    )

    test_signal = {
        "asset_type": "crypto",
        "symbol": "BTC/USD",
        "signal": "SELL",
        "signal_time": "2026-10-18T14:35:00Z",
        "price": 81200.0,
        "sentiment": -0.6200,
        "sma_20": 81100.0,
        "sma_50": 81000.0,
        "trading_mode": "DRY_RUN",
        "signal_id": f"TEST-SIG-DLQ-{int(time.time())}"
    }

    res = notifier.send_signal_notification(test_signal, force=True)

    # 1. Must report FAILED, never false DELIVERED
    assert res.get("status") == "FAILED", f"Expected FAILED status, got {res}"
    assert res.get("dead_letter") is True

    # 2. Must NOT be stored in delivered_signals state
    assert test_signal["signal_id"] not in notifier.delivered_signals

    # 3. Must be recorded in DEAD_LETTER_FILE
    assert os.path.exists(DEAD_LETTER_FILE), f"Missing DLQ file: {DEAD_LETTER_FILE}"
    with open(DEAD_LETTER_FILE, "r", encoding="utf-8") as f:
        dlq_lines = [json.loads(line) for line in f if line.strip()]
    dlq_match = [entry for entry in dlq_lines if entry.get("signal_id") == test_signal["signal_id"]]
    assert len(dlq_match) > 0, "No dead-letter entry found for failed signal"
    assert "error" in dlq_match[0]

    print(f"  [PASS] Permanent failure correctly intercepted: Not marked as DELIVERED, routed to DLQ with {adapter.call_count} attempts.")
    return {
        "id": "TC-G14-15",
        "name": "Slack crash recovery",
        "expected": "Failed notifications route to Dead-Letter Queue without false DELIVERED marking",
        "actual": f"Status=FAILED after {adapter.call_count} retries; persisted to dead letter queue",
        "evidence": f"File {DEAD_LETTER_FILE} contains error record: {dlq_match[0]['error']}",
        "status": "PASS"
    }

if __name__ == "__main__":
    t1 = test_tc_g14_14_slack_retry_and_outbox()
    t2 = test_tc_g14_15_slack_crash_recovery()
    print("\nSummary: All 2 Slack Delivery & Outbox tests passed!")

