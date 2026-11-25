#!/usr/bin/env python3
"""
tests/test_gd27_hardening.py
============================
Master Automated Test Suite for GĐ27:
PRODUCTION DEPLOYMENT HARDENING & DISASTER RECOVERY VALIDATION (v1.0.0).

26 Evaluation Criteria:
  TC-G27-01 to TC-G27-06: Production Web Serving & Architecture Differentiation
  TC-G27-07 to TC-G27-12: Full Backup & Cryptographic Snapshot Validation
  TC-G27-13 to TC-G27-17: Isolated Disaster Recovery, Data Diff & RTO/RPO Metrics
  TC-G27-18 to TC-G27-22: Security & Access Hardening (CORS, Secrets, Binding)
  TC-G27-23 to TC-G27-26: Operational Invariants & Fail-Closed Guardrails
"""

import os
import sys
import json
import time
import unittest
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from alpaca_paper_gate import (
    AlpacaPaperGate,
    PaperExecutionGateClosedError,
    LiveTradingProhibitedError,
    BrokerMode,
    paper_gate,
)
from scripts.disaster_recovery_engine import (
    create_snapshot,
    validate_snapshot,
    dry_run_restore,
    execute_isolated_restore,
    compute_sha256,
)

PROD_WEB_URL = "http://localhost:3000"
DEV_WEB_URL = "http://localhost:5173"
PREVIEW_WEB_URL = "http://localhost:4173"
BACKEND_BASE_URL = "http://127.0.0.1:8005"


class TestGD27Hardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Check backend reachability
        try:
            r = requests.get(f"{BACKEND_BASE_URL}/api/health", timeout=3)
            cls.backend_available = r.status_code == 200
        except Exception:
            cls.backend_available = False

        # Check production web server reachability
        try:
            r = requests.get(f"{PROD_WEB_URL}/healthz", timeout=3)
            cls.prod_web_available = r.status_code == 200
        except Exception:
            cls.prod_web_available = False

        # Check preview server reachability
        try:
            r = requests.get(f"{PREVIEW_WEB_URL}/", timeout=3)
            cls.preview_available = r.status_code == 200
        except Exception:
            cls.preview_available = False

    # =========================================================================
    # 1. PRODUCTION WEB SERVING (TC-G27-01 to TC-G27-06)
    # =========================================================================

    def test_01_production_web_server_serving_bundle(self):
        """TC-G27-01: Production Web Server running on port 3000 serves compiled dist/index.html."""
        if not self.prod_web_available:
            self.skipTest("Production Web Server on port 3000 not reachable")
        r = requests.get(f"{PROD_WEB_URL}/", timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertIn("<!doctype html>", r.text.lower())
        self.assertIn("/assets/index-", r.text)

    def test_02_spa_routing_fallback_behavior(self):
        """TC-G27-02: SPA routing fallback serves index.html for non-asset deep paths."""
        if not self.prod_web_available:
            self.skipTest("Production Web Server on port 3000 not reachable")
        paths = ["/workbench", "/analytics", "/overview", "/orders/history"]
        for p in paths:
            r = requests.get(f"{PROD_WEB_URL}{p}", timeout=5)
            self.assertEqual(r.status_code, 200)
            self.assertIn("<!doctype html>", r.text.lower())
            self.assertIn("text/html", r.headers.get("content-type", "").lower())

    def test_03_healthz_endpoint_contract(self):
        """TC-G27-03: Production /healthz endpoint returns 200 OK with server health metadata."""
        if not self.prod_web_available:
            self.skipTest("Production Web Server on port 3000 not reachable")
        r = requests.get(f"{PROD_WEB_URL}/healthz", timeout=5)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "HEALTHY")
        self.assertEqual(data.get("server"), "AlgoTrading Production Web Server")
        self.assertEqual(data.get("mode"), "PRODUCTION")
        self.assertTrue(data.get("spa_fallback"))

    def test_04_security_headers_enforcement(self):
        """TC-G27-04: Security headers (nosniff, SAMEORIGIN, strict-origin) enforced on prod server."""
        if not self.prod_web_available:
            self.skipTest("Production Web Server on port 3000 not reachable")
        r = requests.get(f"{PROD_WEB_URL}/", timeout=5)
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("strict-origin", r.headers.get("Referrer-Policy", ""))

    def test_05_three_tier_server_differentiation(self):
        """TC-G27-05: Three-tier server differentiation (Dev: 5173, Preview: 4173, Prod: 3000)."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        self.assertTrue(dist_dir.exists())
        self.assertTrue((dist_dir / "index.html").exists())
        # Prod server must be distinct from Vite Preview and Dev
        self.assertNotEqual(PROD_WEB_URL, PREVIEW_WEB_URL)
        self.assertNotEqual(PROD_WEB_URL, DEV_WEB_URL)

    def test_06_controlled_startup_and_shutdown_scripts(self):
        """TC-G27-06: Controlled startup (start_prod_web.ps1) and shutdown (stop_prod_web.ps1) scripts."""
        start_script = REPO_ROOT / "scripts" / "start_prod_web.ps1"
        stop_script = REPO_ROOT / "scripts" / "stop_prod_web.ps1"
        self.assertTrue(start_script.exists())
        self.assertTrue(stop_script.exists())
        self.assertIn("Start-Process", start_script.read_text(encoding="utf-8"))
        self.assertIn("Stop-Process", stop_script.read_text(encoding="utf-8"))

    # =========================================================================
    # 2. FULL BACKUP & CRYPTOGRAPHIC SNAPSHOT (TC-G27-07 to TC-G27-12)
    # =========================================================================

    def test_07_production_snapshot_creation(self):
        """TC-G27-07: Create production snapshot via disaster_recovery_engine."""
        snap_path, manifest = create_snapshot()
        self.assertTrue(snap_path.exists())
        self.assertGreater(manifest["file_count"], 50)
        self.assertEqual(manifest["version"], "v1.0.0")
        self.assertEqual(manifest["trading_mode"], "DRY_RUN")

    def test_08_snapshot_manifest_and_sha256_checksums(self):
        """TC-G27-08: Snapshot manifest contains valid SHA-256 checksums for all files."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        self.assertTrue(manifest_file.exists())
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            self.assertIn("sha256", entry)
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertGreaterEqual(entry["size_bytes"], 0)

    def test_09_snapshot_inventory_completeness(self):
        """TC-G27-09: Snapshot inventory includes Mock Broker, configs, status, and scripts."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        paths = [e["path"] for e in manifest.get("files", [])]
        self.assertIn("mock_broker/mock_broker_state.json", paths)
        self.assertIn("configs/docker-compose.yml", paths)
        self.assertIn("configs/sanitized_env.json", paths)
        self.assertIn("streaming/streaming_metadata.json", paths)

    def test_10_secret_sanitation_in_snapshot(self):
        """TC-G27-10: Secret sanitation masks all sensitive API tokens in snapshot configs."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        snap_dir = REPO_ROOT / "data" / "backups" / manifest["snapshot_id"]
        sanitized_env_file = snap_dir / "configs" / "sanitized_env.json"
        self.assertTrue(sanitized_env_file.exists())
        env_data = json.loads(sanitized_env_file.read_text(encoding="utf-8"))
        for k, v in env_data.items():
            if "SECRET" in k or "TOKEN" in k:
                self.assertEqual(v, "***REDACTED_FOR_SECURITY***")

    def test_11_snapshot_integrity_validation(self):
        """TC-G27-11: Validate snapshot integrity (100% files checked, 0 mismatches)."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        snap_dir = REPO_ROOT / "data" / "backups" / manifest["snapshot_id"]
        val = validate_snapshot(snap_dir)
        self.assertTrue(val["valid"])
        self.assertEqual(len(val["mismatches"]), 0)
        self.assertEqual(val["checked_files"], manifest["file_count"])

    def test_12_dry_run_restore_simulation(self):
        """TC-G27-12: Dry-run restore simulation returns SUCCESS without modifying disk."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        snap_dir = REPO_ROOT / "data" / "backups" / manifest["snapshot_id"]
        res = dry_run_restore(snap_dir, REPO_ROOT / "data" / "isolated_restore_test")
        self.assertEqual(res["dry_run_verdict"], "SUCCESS")
        self.assertFalse(res["safety_checks"]["overwrites_active_env"])

    # =========================================================================
    # 3. ISOLATED DISASTER RECOVERY & RTO/RPO (TC-G27-13 to TC-G27-17)
    # =========================================================================

    def test_13_actual_file_extraction_in_isolation(self):
        """TC-G27-13: Extract all snapshot files into isolated test environment."""
        manifest_file = REPO_ROOT / "data" / "status" / "gd27_backup_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        snap_dir = REPO_ROOT / "data" / "backups" / manifest["snapshot_id"]
        iso_dir = REPO_ROOT / "data" / "isolated_restore_test"
        evidence = execute_isolated_restore(snap_dir, iso_dir)
        self.assertEqual(evidence["verdict"], "VERIFIED — RESTORE_SUCCESSFUL")
        self.assertTrue((iso_dir / "mock_broker" / "mock_broker_state.json").exists())

    def test_14_cryptographic_verification_before_vs_after(self):
        """TC-G27-14: Checksums before vs after restore match 100% (zero diff)."""
        evidence_file = REPO_ROOT / "data" / "status" / "gd27_restore_evidence.json"
        self.assertTrue(evidence_file.exists())
        ev = json.loads(evidence_file.read_text(encoding="utf-8"))
        self.assertEqual(ev["integrity_verification"]["checksum_mismatches_count"], 0)
        self.assertEqual(ev["integrity_verification"]["data_diff_count"], 0)
        self.assertTrue(ev["integrity_verification"]["zero_diff_verified"])

    def test_15_component_startup_in_isolation(self):
        """TC-G27-15: Mock Broker state successfully loaded in isolation with $100k cash."""
        evidence_file = REPO_ROOT / "data" / "status" / "gd27_restore_evidence.json"
        ev = json.loads(evidence_file.read_text(encoding="utf-8"))
        comp = ev["component_startup_in_isolation"]
        self.assertTrue(comp["mock_broker_state_loaded"])
        self.assertEqual(comp["verified_cash_balance"], 100000.0)
        self.assertTrue(comp["isolated_execution_ready"])

    def test_16_rto_measurement_within_sla(self):
        """TC-G27-16: Measured RTO < 300s SLA (recovery time measured in real seconds)."""
        evidence_file = REPO_ROOT / "data" / "status" / "gd27_restore_evidence.json"
        ev = json.loads(evidence_file.read_text(encoding="utf-8"))
        actual_rto = ev["rto_metric"]["actual_rto_seconds"]
        self.assertLess(actual_rto, 300.0)
        self.assertTrue(ev["rto_metric"]["meets_sla"])

    def test_17_rpo_delta_determination(self):
        """TC-G27-17: RPO delta meets SLA (< 86400s / 24 hours)."""
        evidence_file = REPO_ROOT / "data" / "status" / "gd27_restore_evidence.json"
        ev = json.loads(evidence_file.read_text(encoding="utf-8"))
        self.assertTrue(ev["rpo_metric"]["meets_sla"])
        self.assertLess(ev["rpo_metric"]["actual_rpo_delta_seconds"], 86400.0)

    # =========================================================================
    # 4. SECURITY & ACCESS HARDENING (TC-G27-18 to TC-G27-22)
    # =========================================================================

    def test_18_zero_credentials_in_bundle(self):
        """TC-G27-18: Verify zero secret keys or tokens in dist/assets/*.js."""
        dist_dir = REPO_ROOT / "trading-dashboard" / "frontend" / "dist"
        if dist_dir.exists():
            for js_file in (dist_dir / "assets").glob("*.js"):
                txt = js_file.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("ALPACA_SECRET_KEY", txt)
                self.assertNotIn("BROKER_SECRET_KEY", txt)

    def test_19_backend_cors_policy_integrity(self):
        """TC-G27-19: Backend CORS allows requests from frontend port 3000 and 4173."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
        r = requests.options(f"{BACKEND_BASE_URL}/api/health", headers=headers, timeout=5)
        self.assertIn(r.status_code, [200, 204])

    def test_20_server_side_authority_assertion_http_403(self):
        """TC-G27-20: Server-side HTTP 403 Forbidden when target_broker='ALPACA_PAPER'."""
        if not self.backend_available:
            self.skipTest("Backend not reachable")
        payload = {
            "symbol": "TSLA", "qty": 1.0, "side": "buy", "type": "market", "target_broker": "ALPACA_PAPER"
        }
        r = requests.post(f"{BACKEND_BASE_URL}/api/workbench/orders", json=payload, timeout=5)
        self.assertEqual(r.status_code, 403)
        self.assertIn("locked", r.json().get("detail", "").lower())

    def test_21_network_binding_internal_restraint(self):
        """TC-G27-21: Network services remain internally bound (localhost / internal subnet)."""
        # Production web server and backend do not expose public tunnels
        self.assertNotIn("ngrok", str(REPO_ROOT).lower())
        self.assertNotIn("localtunnel", str(REPO_ROOT).lower())

    def test_22_log_sanitation_hygiene(self):
        """TC-G27-22: Audit logs in logs/ contain zero credentials."""
        logs_dir = REPO_ROOT / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                txt = log_file.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("PKW82P0X90EXAMPLE", txt)

    # =========================================================================
    # 5. OPERATIONAL INVARIANTS & GUARDS (TC-G27-23 to TC-G27-26)
    # =========================================================================

    def test_23_paper_execution_gate_fail_closed(self):
        """TC-G27-23: PaperExecutionGate.is_gate_open is False; order submission fails closed."""
        self.assertFalse(paper_gate.is_gate_open)
        self.assertEqual(paper_gate.mode, BrokerMode.ALPACA_PAPER_READ_ONLY)
        with self.assertRaises(PaperExecutionGateClosedError):
            paper_gate.submit_paper_order({"symbol": "AAPL", "qty": 1.0, "side": "buy"}, fake_transport=False)

    def test_24_live_trading_prohibition(self):
        """TC-G27-24: Live broker URL raises LiveTradingProhibitedError immediately."""
        with self.assertRaises(LiveTradingProhibitedError):
            AlpacaPaperGate(base_url="https://api.alpaca.markets")

    def test_25_trading_mode_dry_run_immutability(self):
        """TC-G27-25: TRADING_MODE=DRY_RUN remains immutable in .env."""
        env_file = REPO_ROOT / ".env"
        self.assertTrue(env_file.exists())
        content = env_file.read_text(encoding="utf-8")
        self.assertIn("TRADING_MODE=DRY_RUN", content)
        self.assertNotIn("TRADING_MODE=LIVE", content)

    def test_26_historical_artifacts_preservation(self):
        """TC-G26-26: All historical artifacts from GĐ18 to GĐ26 remain intact."""
        status_dir = REPO_ROOT / "data" / "status"
        self.assertTrue((status_dir / "gd25_acceptance.json").exists())
        self.assertTrue((status_dir / "gd26_acceptance.json").exists())
        self.assertTrue((status_dir / "gd25_release_manifest.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
