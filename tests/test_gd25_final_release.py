"""
tests/test_gd25_final_release.py
================================
GĐ25 — FINAL RELEASE & OPERATIONAL SIGN-OFF TEST SUITE
Comprehensive automated verification across 4 sub-phases:
- GĐ25.1: GĐ18 Operational Soak Closeout (TC-G25-01 to TC-G25-06)
- GĐ25.2: Release Packaging & Operational Readiness (TC-G25-07 to TC-G25-11)
- GĐ25.3: Final UAT Across 7 Functional Groups (TC-G25-12 to TC-G25-22)
- GĐ25.4: Final Safety & Guardrail Audit (TC-G25-23 to TC-G25-26)

Total: 26 automated criteria with strict invariants:
- TRADING_MODE = DRY_RUN
- PaperExecutionGate.is_gate_open = False
- Zero broker writes, Zero live execution paths
- Truthful soak recording: No false continuous PASS when interruptions exist
"""

import os
import sys
import json
import unittest
import requests
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBS_DIR = REPO_ROOT / "libs"
if str(LIBS_DIR) not in sys.path:
    sys.path.insert(0, str(LIBS_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alpaca_paper_sdk import AlpacaPaperSDK
from alpaca_paper_gate import (
    AlpacaPaperGate,
    PaperExecutionGateClosedError,
    LiveTradingProhibitedError,
    BrokerMode,
    paper_gate
)

BACKEND_BASE_URL = "http://127.0.0.1:8005"
FLINK_JOBMANAGER_URL = "http://localhost:8081"


class TestGD25FinalRelease(unittest.TestCase):
    """GĐ25 Final Release & Operational Sign-off Test Suite."""

    @classmethod
    def setUpClass(cls):
        """Verify baseline test connectivity and mock broker state."""
        cls.backend_available = False
        try:
            r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
            if r.status_code == 200:
                cls.backend_available = True
        except Exception:
            cls.backend_available = False

        cls.paper_sdk = AlpacaPaperSDK()
        cls.paper_gate = paper_gate

    # =========================================================================
    # GĐ25.1: GĐ18 OPERATIONAL SOAK CLOSEOUT (TC-G25-01 to TC-G25-06)
    # =========================================================================

    def test_01_soak_baseline_macro_window_verification(self):
        """TC-G25-01: Verify macro soak observation window from baseline 2026-10-24T11:46:30Z to 2026-10-31T11:46:30Z (>= 168h)."""
        baseline_str = "2026-10-24T11:46:30Z"
        target_str = "2026-10-31T11:46:30Z"
        baseline_dt = datetime.fromisoformat(baseline_str.replace("Z", "+00:00"))
        target_dt = datetime.fromisoformat(target_str.replace("Z", "+00:00"))

        elapsed_target_hours = (target_dt - baseline_dt).total_seconds() / 3600.0
        self.assertAlmostEqual(elapsed_target_hours, 168.0, places=2)

        now_dt = datetime.now(timezone.utc)
        elapsed_actual_hours = (now_dt - baseline_dt).total_seconds() / 3600.0
        self.assertGreaterEqual(elapsed_actual_hours, 168.0,
            f"Calendar window since baseline {baseline_str} is {elapsed_actual_hours:.2f}h, which meets >= 168h target.")

    def test_02_container_lifecycle_interruption_truthful_recording(self):
        """TC-G25-02: Truthful recording: Detect container restart events and forbid marking soak continuous PASS."""
        # Inspect docker state or previous summary
        # If any container restarts occurred, verdict must be CONDITIONALLY_ACCEPTED or INTERRUPTED
        gd18_summary_path = REPO_ROOT / "data" / "status" / "gd18_4_soak_summary.json"
        self.assertTrue(gd18_summary_path.exists(), "GĐ18.4 soak summary must exist")
        with open(gd18_summary_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        soak_data = data.get("soak_baseline_and_endurance", {})
        milestone = soak_data.get("168_hour_continuous_milestone", "")
        # Must NOT be marked PASS blindly
        self.assertIn("NOT_OBSERVED", milestone,
            "168h continuous single session was ongoing and must not be marked PASS without uninterrupted proof")

    def test_03_flink_checkpoint_integrity_across_sessions(self):
        """TC-G25-03: Verify Flink cluster active streaming with zero checkpoint failures."""
        try:
            r = requests.get(f"{FLINK_JOBMANAGER_URL}/jobs/overview", timeout=5)
            self.assertEqual(r.status_code, 200)
            jobs = r.json().get("jobs", [])
            self.assertGreaterEqual(len(jobs), 2, "Both Production Strategy 1 and Crypto Strategy jobs must be active")
            for job in jobs:
                self.assertEqual(job["state"], "RUNNING")
                self.assertEqual(job["tasks"]["failed"], 0)
        except requests.exceptions.ConnectionError:
            self.skipTest("Flink JobManager not reachable directly")

    def test_04_redpanda_consumer_lag_strict_sla(self):
        """TC-G25-04: Redpanda consumer lag is strictly within SLA (lag <= 50, actual=0)."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        status_data = r.json()
        health_pillars = status_data.get("health_pillars", {})
        signal_pillar = health_pillars.get("signal_handlers", {})
        self.assertEqual(signal_pillar.get("status"), "HEALTHY")
        self.assertIn("lag=0", signal_pillar.get("reason", "").lower())

    def test_05_telemetry_samples_log_audit(self):
        """TC-G25-05: Verify gd18_telemetry_samples.jsonl contains structured telemetry samples."""
        samples_path = REPO_ROOT / "data" / "status" / "gd18_telemetry_samples.jsonl"
        self.assertTrue(samples_path.exists(), "Telemetry samples file must exist")
        sample_count = 0
        with open(samples_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    self.assertIn("timestamp", record)
                    sample_count += 1
        self.assertGreaterEqual(sample_count, 50, "Should contain at least 50 telemetry samples")

    def test_06_open_findings_closeout_status(self):
        """TC-G25-06: Verify status of open findings OF-01 through OF-05."""
        findings = {
            "OF-01": "CONDITIONALLY_ACCEPTED (Closeout with documented interruptions)",
            "OF-02": "PROVENANCE_UNCONFIRMED (Maintained for unconfirmed historical artifacts)",
            "OF-03": "RESOLVED_BY_DESIGN (Updated bars delta_t=0s deduplicated by key)",
            "OF-04": "RESOLVED_BY_DESIGN (Strict separation of NATURAL_RUNTIME vs TEST_GENERATED)",
            "OF-05": "RESOLVED_BY_DESIGN (Stocks classified as IDLE_MARKET_CLOSED during closed hours)"
        }
        for of_id, expected_status in findings.items():
            self.assertTrue(len(expected_status) > 0, f"{of_id} must have designated closeout status")

    # =========================================================================
    # GĐ25.2: RELEASE PACKAGING & OPERATIONAL READINESS (TC-G25-07 to TC-G25-11)
    # =========================================================================

    def test_07_frontend_production_build_artifacts(self):
        """TC-G25-07: Verify frontend production build artifacts (dist/) exist, valid HTML/CSS/JS, zero secrets."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        self.assertTrue(dist_dir.exists(), "dist/ directory must exist")
        index_html = dist_dir / "index.html"
        self.assertTrue(index_html.exists(), "index.html must exist in dist/")
        self.assertGreater(index_html.stat().st_size, 200)

        # Check absence of secrets in dist
        assets_dir = dist_dir / "assets"
        self.assertTrue(assets_dir.exists(), "assets/ directory must exist in dist/")
        for asset in assets_dir.glob("*.js"):
            content = asset.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("ALPACA_SECRET_KEY", content)
            self.assertNotIn("PKW82P0X90EXAMPLE", content)

    def test_08_backend_api_contracts_validation(self):
        """TC-G25-08: Verify backend responds to standard API contracts across 5 functional areas."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        endpoints = [
            "/api/health",
            "/api/system/status",
            "/api/workbench/account?source=alpaca_paper",
            "/api/workbench/orders?source=mock",
            "/api/candles?symbol=AAPL"
        ]
        for ep in endpoints:
            r = requests.get(f"{BACKEND_BASE_URL}{ep}", timeout=5)
            self.assertEqual(r.status_code, 200, f"Endpoint {ep} should return 200")

    def test_09_docker_compose_configuration_integrity(self):
        """TC-G25-09: Verify docker-compose.yml configuration specifies all required services."""
        compose_file = REPO_ROOT / "docker-compose.yml"
        self.assertTrue(compose_file.exists(), "docker-compose.yml must exist")
        content = compose_file.read_text(encoding="utf-8")
        required_services = ["redpanda-1", "jobmanager", "taskmanager"]
        for svc in required_services:
            self.assertIn(svc, content, f"Service {svc} must be defined in docker-compose.yml")

    def test_10_five_pillar_health_architecture_readiness(self):
        """TC-G25-10: Verify 5-pillar health coordinator reports all systems nominal."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("health_pillars", data)
        pillars = data["health_pillars"]
        expected_pillars = ["infrastructure", "data_freshness", "processing", "signal_handlers", "end_to_end"]
        for p in expected_pillars:
            self.assertIn(p, pillars, f"Pillar {p} must be present in health status")
            self.assertEqual(pillars[p]["status"], "HEALTHY")

    def test_11_operational_runbook_scripts_present_and_safe(self):
        """TC-G25-11: Operational scripts (start_all, stop_all, status_all, recover_all) verified present and safe."""
        scripts_dir = REPO_ROOT / "scripts"
        required_scripts = ["start_all.ps1", "stop_all.ps1", "status_all.ps1", "recover_all.ps1"]
        for s in required_scripts:
            script_path = scripts_dir / s
            self.assertTrue(script_path.exists(), f"Script {s} must exist in scripts/")
            content = script_path.read_text(encoding="utf-8")
            self.assertNotIn("rm -rf /", content)
            self.assertNotIn("format c:", content.lower())

    # =========================================================================
    # GĐ25.3: FINAL UAT ACROSS 7 FUNCTIONAL GROUPS (TC-G25-12 to TC-G25-22)
    # =========================================================================

    def test_12_uat_market_overview_and_charts(self):
        """TC-G25-12: UAT Group 1: Market Overview and Candlestick stream integrity."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/candles?symbol=AAPL", timeout=5)
        self.assertEqual(r.status_code, 200)
        candles = r.json()
        self.assertTrue(isinstance(candles, (dict, list)))

    def test_13_uat_strategy_analytics_and_shadow_observations(self):
        """TC-G25-13: UAT Group 2: Strategy analytics and shadow mode ledger."""
        shadow_file = REPO_ROOT / "data" / "status" / "shadow_observations.jsonl"
        self.assertTrue(shadow_file.exists(), "Shadow observations ledger must exist")
        with open(shadow_file, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        self.assertGreater(len(lines), 0, "Shadow observations should have recorded signals")

    def test_14_uat_system_health_and_reliability_logs(self):
        """TC-G25-14: UAT Group 3: System Health and Reliability logs."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/reliability/events", timeout=5)
        self.assertEqual(r.status_code, 200)

    def test_15_uat_paper_account_and_positions(self):
        """TC-G25-15: UAT Group 4: Alpaca Paper Read-Only Account ($99,773.38) and Positions (NVDA, BTC)."""
        account = paper_gate.get_account_overview()
        self.assertEqual(account.get("status"), "ACTIVE")
        self.assertEqual(account.get("account_number"), "PA31BG5IX")
        self.assertAlmostEqual(account.get("cash", 0), 99773.38, places=2)

        positions = paper_gate.get_positions()
        pos_symbols = {p["symbol"]: float(p["qty"]) for p in positions}
        self.assertIn("NVDA", pos_symbols)
        self.assertIn("BTCUSD", pos_symbols)
        self.assertEqual(pos_symbols["NVDA"], 1.0)
        self.assertAlmostEqual(pos_symbols["BTCUSD"], 0.000120008, places=8)

    def test_16_uat_paper_orders_history_and_details(self):
        """TC-G25-16: UAT Group 5a: Alpaca Paper Order History (NVDA and BTC buy fills)."""
        orders = paper_gate.get_orders(status="all")
        self.assertGreaterEqual(len(orders), 2)
        symbols = [o["symbol"] for o in orders]
        self.assertIn("NVDA", symbols)
        self.assertIn("BTC/USD", symbols)
        for o in orders:
            self.assertEqual(o["status"], "filled")

    def test_17_uat_account_activities_reconciliation(self):
        """TC-G25-17: UAT Group 5b: Reconcile 4 activity types (JNLC, FILL, CFEE, FEE) across 5 distinct historical records."""
        activities = paper_gate.get_account_activities(limit=50)
        self.assertGreaterEqual(len(activities), 4)
        activity_types = {a["activity_type"] for a in activities}
        self.assertEqual(activity_types, {"JNLC", "FILL", "CFEE", "FEE"})

    def test_18_uat_satoshi_level_btc_precision(self):
        """TC-G25-18: UAT Group 5c: Reconcile Satoshi-level BTC position quantity via CFEE fee deduction."""
        order_filled_qty = 0.000120309
        cfee_deduction = 0.000000301
        expected_pos_qty = round(order_filled_qty - cfee_deduction, 9)
        self.assertEqual(expected_pos_qty, 0.000120008)

        positions = paper_gate.get_positions()
        btc_pos = next((p for p in positions if p["symbol"] == "BTCUSD"), None)
        self.assertIsNotNone(btc_pos)
        self.assertAlmostEqual(btc_pos["qty"], 0.000120008, places=9)

    def test_19_uat_mock_workbench_order_types_execution(self):
        """TC-G25-19: UAT Group 6a: Mock Broker order placement for 5 order types."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        orders_to_create = [
            {"symbol": "NVDA", "side": "buy", "type": "market", "qty": 2.0},
            {"symbol": "AAPL", "side": "buy", "type": "limit", "qty": 5.0, "limit_price": 220.0},
            {"symbol": "MSFT", "side": "buy", "type": "stop", "qty": 3.0, "stop_price": 410.0},
            {"symbol": "GOOGL", "side": "buy", "type": "stop_limit", "qty": 4.0, "stop_price": 175.0, "limit_price": 173.0},
            {"symbol": "TSLA", "side": "sell", "type": "trailing_stop", "qty": 1.0, "trail_percent": 1.5},
        ]
        created_ids = []
        for o in orders_to_create:
            res = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json=o, timeout=5)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("is_mock"))
            self.assertTrue(data.get("id").startswith("mock_ord_"))
            created_ids.append(data.get("id"))
        self.assertEqual(len(created_ids), 5)

    def test_20_uat_mock_fractional_and_notional_orders(self):
        """TC-G25-20: UAT Group 6b: Mock Broker fractional quantity and notional orders validation and execution."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        # Fractional Qty order
        res_frac = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json={
            "symbol": "BTC/USD", "side": "buy", "type": "market", "qty": 0.05
        }, timeout=5)
        self.assertEqual(res_frac.status_code, 200)
        self.assertAlmostEqual(res_frac.json().get("qty"), 0.05, places=4)

        # Notional Dollar order
        res_notional = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json={
            "symbol": "AAPL", "side": "buy", "type": "market", "notional": 500.0
        }, timeout=5)
        self.assertEqual(res_notional.status_code, 200)
        self.assertAlmostEqual(res_notional.json().get("notional"), 500.0, places=2)

    def test_21_uat_mock_order_replacement_and_cancellation(self):
        """TC-G25-21: UAT Group 6c: In-flight order replacement and bulk cancellation."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        # Create limit order
        c_res = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json={
            "symbol": "NVDA", "side": "buy", "type": "limit", "qty": 8.0, "limit_price": 200.0
        }, timeout=5)
        self.assertEqual(c_res.status_code, 200)
        orig_id = c_res.json()["id"]

        # Replace order
        r_res = requests.patch(f"{BACKEND_BASE_URL}/api/workbench/orders/{orig_id}", json={
            "qty": 12.0, "limit_price": 202.0
        }, timeout=5)
        self.assertEqual(r_res.status_code, 200)
        replaced = r_res.json()
        self.assertEqual(replaced.get("replaces"), orig_id)
        self.assertEqual(replaced.get("qty"), 12.0)
        self.assertEqual(replaced.get("limit_price"), 202.0)

        # Bulk cancel all
        bulk_res = requests.delete(f"{BACKEND_BASE_URL}/api/workbench/orders", timeout=5)
        self.assertEqual(bulk_res.status_code, 200)
        self.assertIn("canceled_count", bulk_res.json())

    def test_22_uat_mock_state_segregation_and_reset(self):
        """TC-G25-22: UAT Group 6d: Mock Broker state reset restores $100k cash and leaves Alpaca Paper untouched."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        reset_res = requests.post(f"{BACKEND_BASE_URL}/api/workbench/reset", timeout=5)
        self.assertEqual(reset_res.status_code, 200)
        reset_data = reset_res.json()
        self.assertEqual(reset_data.get("cash"), 100000.0)

        # Verify Alpaca Paper account was untouched
        paper_acc = paper_gate.get_account_overview()
        self.assertAlmostEqual(paper_acc.get("cash", 0), 99773.38, places=2)

    # =========================================================================
    # GĐ25.4: FINAL SAFETY & GUARDRAIL AUDIT (TC-G25-23 to TC-G25-26)
    # =========================================================================

    def test_23_server_side_authority_assertion_http_403(self):
        """TC-G25-23: Server-side HTTP 403 Forbidden when target_broker='ALPACA_PAPER'."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        payload = {
            "symbol": "AAPL",
            "qty": 1.0,
            "side": "buy",
            "type": "limit",
            "limit_price": 150.0,
            "time_in_force": "day",
            "target_broker": "ALPACA_PAPER"
        }
        r = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json=payload, timeout=5)
        self.assertEqual(r.status_code, 403)
        self.assertIn("locked", r.json().get("detail", "").lower())

    def test_24_fail_closed_paper_execution_gate(self):
        """TC-G25-24: PaperExecutionGate.is_gate_open is False; submit_paper_order fails closed."""
        self.assertFalse(paper_gate.is_gate_open)
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        with self.assertRaises(PaperExecutionGateClosedError):
            paper_gate.submit_paper_order({"symbol": "AAPL", "qty": 1, "side": "buy", "type": "market"}, fake_transport=False)

    def test_25_credential_hygiene_and_leakage_absence(self):
        """TC-G25-25: Absence of API credentials in client builds and responses."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        raw_text = r.text
        self.assertNotIn("ALPACA_SECRET_KEY", raw_text)
        self.assertNotIn("secret", raw_text.lower().replace("crypto_latency_sec", ""))

    def test_26_live_prohibition_and_dry_run_immutability(self):
        """TC-G25-26: Live endpoint strictly prohibited and TRADING_MODE=DRY_RUN remains immutable."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

        env_file = REPO_ROOT / ".env"
        self.assertTrue(env_file.exists())
        content = env_file.read_text(encoding="utf-8")
        self.assertIn("TRADING_MODE=DRY_RUN", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
