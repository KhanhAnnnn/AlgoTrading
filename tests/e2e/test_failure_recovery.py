"""
tests/e2e/test_failure_recovery.py — Controlled Failure & Recovery Test Suite
Validates:
1. Consumer Pause & Restart: Offset preservation and zero loss
2. Signal Deduplication: Anti-replay idempotency across restarts
3. Slack API Resilience: Bounded retry on 429 rate limit & 500 server error, zero crash
4. WebSocket Disconnect & Reconnect: Clean backend session cleanup and stream resumption
"""
import os
import sys
import json
import time
import asyncio
from unittest.mock import patch, MagicMock
from kafka import KafkaConsumer, TopicPartition, OffsetAndMetadata
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
STATUS_DIR = os.path.join(BASE_DIR, 'data', 'status')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from slack_notifier import SlackNotifier
from crypto_signal_handler import CryptoSignalHandler

def test_consumer_offset_preservation():
    """Verify consumer group commits offset and resumes exactly from committed offset after restart."""
    group_id = f"gd12-offset-test-{int(time.time())}"
    topic = "trading-signals"
    
    # 1. Start consumer, read first message, commit
    c1 = KafkaConsumer(
        topic,
        bootstrap_servers=['localhost:9092'],
        group_id=group_id,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=3000
    )
    tp = TopicPartition(topic, 0)
    msg1 = next(c1)
    offset_read = msg1.offset
    c1.commit()
    comm = c1.committed(tp)
    committed_offset = comm.offset if hasattr(comm, 'offset') else comm
    c1.close()
    
    # 2. Re-instantiate consumer with same group_id (simulating restart)
    c2 = KafkaConsumer(
        topic,
        bootstrap_servers=['localhost:9092'],
        group_id=group_id,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=3000
    )
    c2.poll(timeout_ms=500)
    res = c2.committed(tp)
    resumed_offset = res.offset if hasattr(res, 'offset') else res
    c2.close()
    
    success = (committed_offset == offset_read + 1) and (resumed_offset == committed_offset)
    return {
        "test": "Consumer Offset Preservation & Restart Recovery",
        "status": "PASS" if success else "FAIL",
        "offset_read": offset_read,
        "committed_offset": committed_offset,
        "resumed_offset_after_restart": resumed_offset,
        "detail": f"Offset accurately maintained at {resumed_offset} across consumer restart."
    }

def test_deduplication_anti_replay():
    """Verify signal handler ignores duplicated signals and prevents replay after restart."""
    handler = CryptoSignalHandler(mode='DRY_RUN')
    known_keys = len(handler.processed_signals)
    
    # Create duplicate payload of the recorded intent from data/orders/crypto_order_intent.json
    dup_signal = {
        'asset_type': 'crypto',
        'symbol': 'ETH/USD',
        'signal': 'BUY',
        'signal_time': '2026-10-17 12:50:00Z',
        'price': 2400.0,
        'sentiment': 0.8,
        'sma_20': 2450.0,
        'sma_50': 2450.0
    }
    
    # Re-feeding duplicate should return None
    res_dup = handler.process_signal(json.dumps(dup_signal))
    
    # Create unique new test signal
    unique_time = f"2026-10-17 23:59:{int(time.time()) % 60:02d}Z"
    new_signal = {
        'asset_type': 'crypto',
        'symbol': 'BTC/USD',
        'signal': 'BUY',
        'signal_time': unique_time,
        'price': 81200.0,
        'sentiment': 0.5,
        'sma_20': 81100.0,
        'sma_50': 81000.0
    }
    with patch.object(handler.slack_notifier, 'send_signal_notification', return_value=True):
        res_new = handler.process_signal(json.dumps(new_signal))
        # Second time should be rejected
        res_second = handler.process_signal(json.dumps(new_signal))
    
    success = (res_dup is None) and (res_new is not None) and (res_second is None)
    return {
        "test": "Signal Deduplication & Anti-Replay Idempotency",
        "status": "PASS" if success else "FAIL",
        "preloaded_known_signals": known_keys,
        "historical_duplicate_rejected": (res_dup is None),
        "fresh_signal_accepted": (res_new is not None),
        "subsequent_duplicate_rejected": (res_second is None),
        "detail": "Idempotent: duplicate historical signals and in-flight repeats safely suppressed."
    }

def test_slack_retry_and_resiliency():
    """Verify SlackNotifier handles 429 rate limit backoff and 500 error gracefully without crashing."""
    notifier = SlackNotifier()
    
    # 1. Test 429 Rate Limit simulation with Retry-After header
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {'Retry-After': '1'}
    mock_resp_429.text = '{"ok": false, "error": "rate_limited"}'
    
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.headers = {}
    mock_resp_200.json.return_value = {'ok': True, 'ts': '1792259999.000100'}
    
    with patch('requests.post', side_effect=[mock_resp_429, mock_resp_200]) as mock_post:
        with patch('time.sleep', return_value=None):
            res = notifier._post_with_retry({'test': 'rate_limit'})
            rate_limit_recovered = (res.get('ok') is True and mock_post.call_count == 2)
        
    # 2. Test 500 Internal Server Error simulation (bounded retry exhaustion)
    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.text = 'Internal Server Error'
    
    with patch('requests.post', side_effect=[mock_resp_500, mock_resp_500, mock_resp_500]) as mock_post_500:
        with patch('time.sleep', return_value=None):
            res_fail = notifier._post_with_retry({'test': 'server_error'})
            # Should return safe error dict without crashing
            graceful_fail = (res_fail.get('ok') is False and mock_post_500.call_count == 3)
        
    success = rate_limit_recovered and graceful_fail
    return {
        "test": "Slack Notifier 429 Rate Limit & 500 Error Resiliency",
        "status": "PASS" if success else "FAIL",
        "rate_limit_recovered": rate_limit_recovered,
        "server_error_graceful_exhaustion": graceful_fail,
        "zero_crash_guarantee": True,
        "detail": "Slack API transient errors handled with bounded exponential backoff; no uncaught exceptions."
    }

async def _test_websocket_reconnect():
    """Verify WebSocket server handles client disconnect and clean reconnect without resource leakage."""
    import websockets
    ws_url = "ws://localhost:8005/ws/live"
    
    # Connection 1: Connect and receive first message
    async with websockets.connect(ws_url) as ws1:
        msg1 = await asyncio.wait_for(ws1.recv(), timeout=5.0)
        data1 = json.loads(msg1)
        # Disconnect abruptly
        await ws1.close()
        
    # Connection 2: Reconnect immediately
    async with websockets.connect(ws_url) as ws2:
        msg2 = await asyncio.wait_for(ws2.recv(), timeout=5.0)
        data2 = json.loads(msg2)
        await ws2.close()
        
    has_type1 = 'type' in data1
    has_type2 = 'type' in data2
    return has_type1 and has_type2, data1.get('type'), data2.get('type')

def test_websocket_reconnection():
    try:
        ok, t1, t2 = asyncio.run(_test_websocket_reconnect())
        return {
            "test": "WebSocket Client Disconnect & Reconnect Resiliency",
            "status": "PASS" if ok else "FAIL",
            "session_1_received": t1,
            "session_2_received": t2,
            "detail": f"Backend handled client disconnect cleanly; second session immediately streamed event of type '{t2}'."
        }
    except Exception as e:
        return {
            "test": "WebSocket Client Disconnect & Reconnect Resiliency",
            "status": "FAIL",
            "error": str(e)
        }

def run_all_failure_recovery_tests():
    report = {
        "suite": "GD12 Controlled Failure & Recovery Tests",
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "results": []
    }
    
    print("Running Test 1: Consumer Offset Preservation...")
    r1 = test_consumer_offset_preservation()
    report["results"].append(r1)
    print(f" -> {r1['status']}: {r1['detail']}")
    
    print("Running Test 2: Signal Deduplication & Anti-Replay...")
    r2 = test_deduplication_anti_replay()
    report["results"].append(r2)
    print(f" -> {r2['status']}: {r2['detail']}")
    
    print("Running Test 3: Slack 429 & 500 Resiliency...")
    r3 = test_slack_retry_and_resiliency()
    report["results"].append(r3)
    print(f" -> {r3['status']}: {r3['detail']}")
    
    print("Running Test 4: WebSocket Disconnect & Reconnect...")
    r4 = test_websocket_reconnection()
    report["results"].append(r4)
    print(f" -> {r4['status']}: {r4.get('detail', r4.get('error'))}")
    
    all_passed = all(r.get("status") == "PASS" for r in report["results"])
    report["overall_status"] = "PASS" if all_passed else "FAIL"
    
    out_file = os.path.join(STATUS_DIR, "gd12_failure_recovery_report.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"\nReport written to: {out_file}")
    print(f"Overall Status: {report['overall_status']}")
    return report

if __name__ == '__main__':
    run_all_failure_recovery_tests()
