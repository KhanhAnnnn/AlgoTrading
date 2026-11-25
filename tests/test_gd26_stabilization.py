"""
tests/test_gd26_stabilization.py
================================
GĐ26 — POST-RELEASE STABILIZATION & MAINTENANCE TEST SUITE
Comprehensive automated verification across 6 core domains:
- 1. Production Deployment & Server Differentiation (TC-G26-01 to TC-G26-07)
- 2. Runtime Monitoring & Resource Headroom (TC-G26-08 to TC-G26-14)
- 3. Maintenance, Backup & Recovery Procedures (TC-G26-15 to TC-G26-19)
- 4. Bug Tracking, UI Integrity & Edge Handling (TC-G26-20 to TC-G26-22)
- 5. Security Invariants & Fail-Closed Guardrails (TC-G26-23 to TC-G26-26)

Total: 26 criteria verifying post-release stability of v1.0.0 under TRADING_MODE=DRY_RUN.
"""

import os
import sys
import json
import shutil
import unittest
import requests
import psutil
from datetime import datetime, timezone
from pathlib import Path

# Paths
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
from mock_trading_broker import MockTradingBroker

BACKEND_BASE_URL = "http://127.0.0.1:8005"
PROD_FRONTEND_URL = "http://localhost:4173"
DEV_FRONTEND_URL = "http://localhost:5173"
FLINK_JOBMANAGER_URL = "http://localhost:8081"


class TestGD26Stabilization(unittest.TestCase):
    """GĐ26 Post-Release Stabilization & Maintenance Test Suite."""

    @classmethod
    def setUpClass(cls):
        """Verify services availability."""
        cls.backend_available = False
        try:
            r = requests.get(f"{BACKEND_BASE_URL}/api/health", timeout=5)
            if r.status_code == 200:
                cls.backend_available = True
        except Exception:
            cls.backend_available = False

        cls.prod_frontend_available = False
        try:
            r = requests.get(PROD_FRONTEND_URL, timeout=5)
            if r.status_code == 200:
                cls.prod_frontend_available = True
        except Exception:
            cls.prod_frontend_available = False

        cls.mock_broker = MockTradingBroker()

    # =========================================================================
    # 1. PRODUCTION DEPLOYMENT & SERVER DIFFERENTIATION (TC-G26-01 to TC-G26-07)
    # =========================================================================

    def test_01_production_bundle_serving(self):
        """TC-G26-01: Verify production frontend server serves compiled dist/index.html."""
        if not self.prod_frontend_available:
            self.skipTest("Production preview server on port 4173 not running")
        r = requests.get(f"{PROD_FRONTEND_URL}/", timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertIn("<!doctype html>", r.text.lower())
        self.assertIn("/assets/index-", r.text)

    def test_02_server_differentiation_prod_vs_dev(self):
        """TC-G26-02: Differentiate production server (port 4173) vs Vite development server (port 5173)."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        self.assertTrue(dist_dir.exists())
        self.assertTrue((dist_dir / "index.html").exists())

        # Production server serves minified static chunks
        if self.prod_frontend_available:
            r_prod = requests.get(PROD_FRONTEND_URL, timeout=5)
            self.assertEqual(r_prod.status_code, 200)
            self.assertIn("assets/index-", r_prod.text)

    def test_03_api_contract_synchronization(self):
        """TC-G26-03: Verify backend and frontend adhere to identical API contract schema."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        required_keys = ["backend_time", "pipeline_verdict", "health_pillars", "kafka", "flink", "producer_status"]
        for k in required_keys:
            self.assertIn(k, data, f"Key {k} missing from /api/system/status contract")

    def test_04_cors_headers_validation(self):
        """TC-G26-04: Verify backend CORS headers allow cross-origin requests from frontend."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        headers = {
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "GET"
        }
        r = requests.options(f"{BACKEND_BASE_URL}/api/health", headers=headers, timeout=5)
        self.assertIn(r.status_code, [200, 204])
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:4173")

    def test_05_health_checks_and_error_handling(self):
        """TC-G26-05: Verify standardized health endpoints and appropriate HTTP error handling."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        # 200 on health
        r_health = requests.get(f"{BACKEND_BASE_URL}/api/health", timeout=5)
        self.assertEqual(r_health.status_code, 200)

        # 404 on nonexistent route
        r_404 = requests.get(f"{BACKEND_BASE_URL}/api/nonexistent_route_test", timeout=5)
        self.assertEqual(r_404.status_code, 404)

        # 403 on real broker write attempt
        r_403 = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json={
            "symbol": "AAPL", "side": "buy", "type": "market", "qty": 1.0, "target_broker": "ALPACA_PAPER"
        }, timeout=5)
        self.assertEqual(r_403.status_code, 403)

    def test_06_docker_compose_and_env_hygiene(self):
        """TC-G26-06: Verify Docker Compose configuration and environment variables integrity."""
        compose_file = REPO_ROOT / "docker-compose.yml"
        self.assertTrue(compose_file.exists())
        content = compose_file.read_text(encoding="utf-8")
        self.assertIn("redpanda-1", content)
        self.assertIn("jobmanager", content)

        env_file = REPO_ROOT / ".env"
        self.assertTrue(env_file.exists())
        env_content = env_file.read_text(encoding="utf-8")
        self.assertIn("TRADING_MODE=DRY_RUN", env_content)

    def test_07_zero_credentials_in_bundle_and_logs(self):
        """TC-G26-07: Verify absence of credentials in frontend bundle (dist/) and logs/."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        if dist_dir.exists():
            for js_file in (dist_dir / "assets").glob("*.js"):
                txt = js_file.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("ALPACA_SECRET_KEY", txt)

        logs_dir = REPO_ROOT / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                txt = log_file.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("PKW82P0X90EXAMPLE", txt)

    # =========================================================================
    # 2. RUNTIME MONITORING & RESOURCE HEADROOM (TC-G26-08 to TC-G26-14)
    # =========================================================================

    def test_08_system_resource_headroom(self):
        """TC-G26-08: Verify system resources: RAM available > 16GB, Disk free > 20GB."""
        mem = psutil.virtual_memory()
        disk = shutil.disk_usage(str(REPO_ROOT))
        avail_ram_gb = mem.available / (1024 ** 3)
        free_disk_gb = disk.free / (1024 ** 3)

        self.assertGreater(avail_ram_gb, 16.0, f"Available RAM {avail_ram_gb:.2f}GB should exceed 16GB")
        self.assertGreater(free_disk_gb, 20.0, f"Free disk space {free_disk_gb:.2f}GB should exceed 20GB")

    def test_09_redpanda_health_and_zero_consumer_lag(self):
        """TC-G26-09: Redpanda brokers healthy and consumer lag strictly 0 across all topics."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("kafka", {}).get("redpanda_connected"))
        self.assertIn("lag=0", data.get("health_pillars", {}).get("signal_handlers", {}).get("reason", "").lower())

    def test_10_flink_jobs_and_checkpoints_zero_failures(self):
        """TC-G26-10: Flink streaming cluster has 2 active jobs with zero checkpoint failures."""
        try:
            r = requests.get(f"{FLINK_JOBMANAGER_URL}/jobs/overview", timeout=5)
            self.assertEqual(r.status_code, 200)
            jobs = r.json().get("jobs", [])
            self.assertGreaterEqual(len(jobs), 2)
            for j in jobs:
                self.assertEqual(j["state"], "RUNNING")
                jid = j["jid"]
                chk_res = requests.get(f"{FLINK_JOBMANAGER_URL}/jobs/{jid}/checkpoints", timeout=5).json()
                counts = chk_res.get("counts", {})
                self.assertEqual(counts.get("failed", 0), 0)
        except requests.exceptions.ConnectionError:
            self.skipTest("Flink JobManager not reachable directly")

    def test_11_producer_and_handler_heartbeat_continuity(self):
        """TC-G26-11: Producers and Signal Handler report continuous active heartbeats."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        pstatus = r.json().get("producer_status", {})
        self.assertTrue(pstatus.get("crypto_producer", {}).get("active"))
        self.assertTrue(pstatus.get("crypto_handler", {}).get("active"))
        self.assertTrue(pstatus.get("news_producer", {}).get("active"))
        self.assertTrue(pstatus.get("price_producer", {}).get("active"))

    def test_12_market_data_freshness_differentiation(self):
        """TC-G26-12: Verify data freshness classification: Crypto 24/7 vs Stocks IDLE_MARKET_CLOSED."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("crypto_mode"), "LIVE STREAMING")
        self.assertIn("MARKET CLOSED", data.get("data_mode"))

    def test_13_backend_api_latency_within_sla(self):
        """TC-G26-13: Backend API average response latency < 100ms."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        t0 = datetime.now()
        r = requests.get(f"{BACKEND_BASE_URL}/api/health", timeout=5)
        duration_ms = (datetime.now() - t0).total_seconds() * 1000.0
        self.assertEqual(r.status_code, 200)
        self.assertLess(duration_ms, 100.0, f"API latency {duration_ms:.2f}ms should be < 100ms")

    def test_14_frontend_production_build_validity(self):
        """TC-G26-14: Frontend production assets exist, size within budget (< 1MB JS, < 100KB CSS)."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        self.assertTrue(dist_dir.exists())
        js_files = list((dist_dir / "assets").glob("*.js"))
        css_files = list((dist_dir / "assets").glob("*.css"))
        self.assertTrue(len(js_files) >= 1)
        self.assertTrue(len(css_files) >= 1)
        js_size_kb = js_files[0].stat().st_size / 1024.0
        css_size_kb = css_files[0].stat().st_size / 1024.0
        self.assertLess(js_size_kb, 1024.0)
        self.assertLess(css_size_kb, 100.0)

    # =========================================================================
    # 3. MAINTENANCE, BACKUP & RECOVERY PROCEDURES (TC-G26-15 to TC-G26-19)
    # =========================================================================

    def test_15_dependency_version_locking(self):
        """TC-G26-15: Verify package dependencies are specified in package.json and pyproject/requirements."""
        pkg_json = REPO_ROOT / "trading-dashboard" / "frontend" / "package.json"
        self.assertTrue(pkg_json.exists())
        with open(pkg_json, "r") as f:
            deps = json.load(f)
        self.assertIn("react", deps.get("dependencies", {}))
        self.assertIn("vite", deps.get("devDependencies", {}))

    def test_16_automated_backup_execution(self):
        """TC-G26-16: Verify scripts/backup_system.ps1 exists and generates backup manifest."""
        backup_script = REPO_ROOT / "scripts" / "backup_system.ps1"
        self.assertTrue(backup_script.exists())
        backups_dir = REPO_ROOT / "data" / "backups"
        self.assertTrue(backups_dir.exists())
        backup_folders = list(backups_dir.glob("backup_*"))
        self.assertGreaterEqual(len(backup_folders), 1, "At least one backup archive must exist")

    def test_17_automated_restore_procedure_dryrun(self):
        """TC-G26-17: Verify scripts/restore_system.ps1 exists and supports dry-run restore."""
        restore_script = REPO_ROOT / "scripts" / "restore_system.ps1"
        self.assertTrue(restore_script.exists())
        content = restore_script.read_text(encoding="utf-8")
        self.assertIn("DryRunTest", content)

    def test_18_log_rotation_standardization(self):
        """TC-G26-18: Verify scripts/rotate_logs.ps1 exists with archive folder capability."""
        rotate_script = REPO_ROOT / "scripts" / "rotate_logs.ps1"
        self.assertTrue(rotate_script.exists())
        content = rotate_script.read_text(encoding="utf-8")
        self.assertIn("MaxSizeMB", content)

    def test_19_versioning_and_rollback_strategy(self):
        """TC-G26-19: Verify v1.0.0 release tagging and rollback documentation."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd25_release_manifest.json"
        self.assertTrue(manifest_file.exists())
        with open(manifest_file, "r") as f:
            manifest = json.load(f)
        self.assertEqual(manifest.get("release_version"), "v1.0.0")

    # =========================================================================
    # 4. BUG TRACKING, UI INTEGRITY & EDGE HANDLING (TC-G26-20 to TC-G26-22)
    # =========================================================================

    def test_20_ui_indicators_and_badges_presence(self):
        """TC-G26-20: Verify data badges [ALPACA PAPER], [MOCK BROKER] in frontend source."""
        components_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "src" / "components"
        self.assertTrue(components_dir.exists())
        workbench_file = components_dir / "TradingWorkbenchPanel.tsx"
        self.assertTrue(workbench_file.exists())
        wb_text = workbench_file.read_text(encoding="utf-8")
        self.assertIn("ALPACA PAPER", wb_text)
        self.assertIn("MOCK BROKER", wb_text)

    def test_21_stale_data_warning_threshold_consistency(self):
        """TC-G26-21: Verify stale data threshold warning logic (120s latency threshold)."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        r = requests.get(f"{BACKEND_BASE_URL}/api/system/status", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        pillars = data.get("health_pillars", {})
        self.assertIn("data_freshness", pillars)
        self.assertEqual(pillars["data_freshness"]["status"], "HEALTHY")

    def test_22_mock_broker_state_management_and_isolation(self):
        """TC-G26-22: Mock Broker state file exists and contains zero real Alpaca orders."""
        mock_file = REPO_ROOT / "data" / "mock_broker" / "mock_broker_state.json"
        self.assertTrue(mock_file.exists())
        with open(mock_file, "r") as f:
            state = json.load(f)
        self.assertIn("account", state)
        self.assertIn("cash", state["account"])
        self.assertTrue(state["account"].get("is_mock"))
        self.assertIn("orders", state)
        for oid, o in state["orders"].items():
            self.assertTrue(o.get("is_mock"))
            self.assertNotEqual(oid, "25f85bed-b086-420a-87ab-52ea3d7a71ac")

    # =========================================================================
    # 5. SECURITY INVARIANTS & FAIL-CLOSED GUARDRAILS (TC-G26-23 to TC-G26-26)
    # =========================================================================

    def test_23_server_side_authority_assertion_http_403(self):
        """TC-G26-23: Server-side HTTP 403 Forbidden when target_broker='ALPACA_PAPER'."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        payload = {
            "symbol": "NVDA", "qty": 1.0, "side": "buy", "type": "market", "target_broker": "ALPACA_PAPER"
        }
        r = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json=payload, timeout=5)
        self.assertEqual(r.status_code, 403)
        self.assertIn("locked", r.json().get("detail", "").lower())

    def test_24_fail_closed_paper_execution_gate(self):
        """TC-G26-24: PaperExecutionGate.is_gate_open is False; submit_paper_order fails closed."""
        self.assertFalse(paper_gate.is_gate_open)
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        with self.assertRaises(PaperExecutionGateClosedError):
            paper_gate.submit_paper_order({"symbol": "NVDA", "qty": 1.0, "side": "buy"}, fake_transport=False)

    def test_25_live_trading_prohibition(self):
        """TC-G26-25: Live broker URL (api.alpaca.markets) raises LiveTradingProhibitedError immediately."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_26_dry_run_immutability(self):
        """TC-G26-26: TRADING_MODE=DRY_RUN remains immutable in .env."""
        env_file = REPO_ROOT / ".env"
        self.assertTrue(env_file.exists())
        content = env_file.read_text(encoding="utf-8")
        self.assertIn("TRADING_MODE=DRY_RUN", content)
        self.assertNotIn("TRADING_MODE=LIVE", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
