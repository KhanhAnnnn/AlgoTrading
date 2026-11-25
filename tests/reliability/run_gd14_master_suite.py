"""
run_gd14_master_suite.py — Master Test Runner for GĐ14 Acceptance
Executes all 22 test cases across the 6 reliability test modules:
1. test_runtime_baseline_and_kafka.py (TC-G14-01, TC-G14-02, TC-G14-07, TC-G14-21)
2. test_producers_fault_tolerance.py (TC-G14-03, TC-G14-04, TC-G14-05, TC-G14-06)
3. test_flink_checkpoint_and_state.py (TC-G14-08, TC-G14-09, TC-G14-10, TC-G14-11)
4. test_consumer_and_signal_reliability.py (TC-G14-12, TC-G14-13, TC-G14-20)
5. test_slack_delivery_and_outbox.py (TC-G14-14, TC-G14-15)
6. test_alpaca_order_safety.py (TC-G14-16, TC-G14-17)
7. test_backend_and_system_stability.py (TC-G14-18, TC-G14-19, TC-G14-22)

Generates machine-readable output: data/status/gd14_master_acceptance_report.json
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATUS_DIR = os.path.join(BASE_DIR, "data", "status")
os.makedirs(STATUS_DIR, exist_ok=True)

# Import test functions
from test_runtime_baseline_and_kafka import (
    test_tc_g14_01_baseline_snapshot,
    test_tc_g14_02_kafka_connectivity,
    test_tc_g14_07_kafka_offset_persistence,
    test_tc_g14_21_stocks_crypto_isolation
)
from test_producers_fault_tolerance import (
    test_tc_g14_03_producer_state_recovery,
    test_tc_g14_04_price_backfill,
    test_tc_g14_05_news_dedup,
    test_tc_g14_06_crypto_websocket_reconnect
)
from test_flink_checkpoint_and_state import (
    test_tc_g14_08_flink_checkpoint_creation,
    test_tc_g14_09_flink_state_restore,
    test_tc_g14_10_sma_state_recovery,
    test_tc_g14_11_sentiment_state_recovery
)
from test_consumer_and_signal_reliability import (
    test_tc_g14_12_handler_restart,
    test_tc_g14_13_signal_dedup_after_restart,
    test_tc_g14_20_zero_unintended_orders
)
from test_slack_delivery_and_outbox import (
    test_tc_g14_14_slack_retry_and_outbox,
    test_tc_g14_15_slack_crash_recovery
)
from test_alpaca_order_safety import (
    test_tc_g14_16_alpaca_idempotency,
    test_tc_g14_17_unknown_order_status_handling
)
from test_backend_and_system_stability import (
    test_tc_g14_18_backend_restart,
    test_tc_g14_19_websocket_resync,
    test_tc_g14_22_resource_and_memory_stability
)

def main():
    timestamp = datetime.now(timezone.utc).isoformat()
    print("=" * 70)
    print(f"STARTING GĐ14 MASTER ACCEPTANCE TEST SUITE AT {timestamp}")
    print("=" * 70)

    test_registry = [
        ("TC-G14-01", test_tc_g14_01_baseline_snapshot),
        ("TC-G14-02", test_tc_g14_02_kafka_connectivity),
        ("TC-G14-03", test_tc_g14_03_producer_state_recovery),
        ("TC-G14-04", test_tc_g14_04_price_backfill),
        ("TC-G14-05", test_tc_g14_05_news_dedup),
        ("TC-G14-06", test_tc_g14_06_crypto_websocket_reconnect),
        ("TC-G14-07", test_tc_g14_07_kafka_offset_persistence),
        ("TC-G14-08", test_tc_g14_08_flink_checkpoint_creation),
        ("TC-G14-09", test_tc_g14_09_flink_state_restore),
        ("TC-G14-10", test_tc_g14_10_sma_state_recovery),
        ("TC-G14-11", test_tc_g14_11_sentiment_state_recovery),
        ("TC-G14-12", test_tc_g14_12_handler_restart),
        ("TC-G14-13", test_tc_g14_13_signal_dedup_after_restart),
        ("TC-G14-14", test_tc_g14_14_slack_retry_and_outbox),
        ("TC-G14-15", test_tc_g14_15_slack_crash_recovery),
        ("TC-G14-16", test_tc_g14_16_alpaca_idempotency),
        ("TC-G14-17", test_tc_g14_17_unknown_order_status_handling),
        ("TC-G14-18", test_tc_g14_18_backend_restart),
        ("TC-G14-19", test_tc_g14_19_websocket_resync),
        ("TC-G14-20", test_tc_g14_20_zero_unintended_orders),
        ("TC-G14-21", test_tc_g14_21_stocks_crypto_isolation),
        ("TC-G14-22", test_tc_g14_22_resource_and_memory_stability),
    ]

    results = []
    passed = 0
    failed = 0

    for test_id, func in test_registry:
        print(f"\n--- Running {test_id} ---")
        try:
            res = func()
            if res.get("status") == "PASS":
                passed += 1
            else:
                failed += 1
            results.append(res)
        except Exception as e:
            failed += 1
            err_res = {
                "id": test_id,
                "name": func.__name__,
                "expected": "Test succeeds without exception",
                "actual": f"Exception raised: {str(e)}",
                "evidence": f"Traceback error: {e}",
                "status": "FAIL"
            }
            results.append(err_res)
            print(f"  [FAIL] {test_id} failed with error: {e}")

    report = {
        "suite": "GD14 System Reliability, Fault Tolerance & Recovery Acceptance",
        "timestamp": timestamp,
        "total_cases": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": round((passed / len(results)) * 100, 2),
        "cases": results,
        "overall_status": "PASS" if failed == 0 else "FAIL"
    }

    report_path = os.path.join(STATUS_DIR, "gd14_master_acceptance_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 70)
    print(f"GĐ14 MASTER SUITE SUMMARY: {passed}/{len(results)} PASSED ({report['pass_rate_pct']}%)")
    print(f"Report saved to: {report_path}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()

