# GĐ40 — Demonstration Fallback & Contingency Plan (Saturday, 28/11/2026)

## 1. Purpose & Risk Mitigation Strategy

During a live technical demonstration, unforeseen hardware, environmental, or process glitches can occur. This document defines the immediate fallback procedures, pre-rendered evidence artifacts, and contingency paths for every subsystem demonstrated in AlgoTrading V2.0.

---

## 2. Contingency Matrix & Rapid Remediation

| Potential Failure Event | Severity | Root Cause Indicator | Immediate Remediation Action | Fallback Asset / Offline Script |
| :--- | :---: | :--- | :--- | :--- |
| **Port `8005` or `5173` Conflict** | Medium | `Address already in use` error on startup | Kill orphan processes via PowerShell one-liner:<br/>`Get-Process -Id (Get-NetTCPConnection -LocalPort 8005).OwningProcess \| Stop-Process -Force` | Rerun `run-dashboard.ps1` |
| **FastAPI Backend Crash / Error 500** | High | Unhandled exception in API route | Restart uvicorn without `--reload`:<br/>`python -m uvicorn libs.bot.api.main:app --port 8005` | SQLite database persists state; frontend auto-reconnects on reload |
| **Vite Dev Server Fails to Compile** | Medium | Node module lock or cache error | Serve pre-built production static files:<br/>`cd trading-dashboard/frontend`<br/>`npm run preview -- --port 5173` | Or Python static server:<br/>`python -m http.server 5173 --directory trading-dashboard/frontend/dist` |
| **WebSocket Stream Disconnects** | Low | Browser socket timeout or network drop | Frontend has built-in auto-reconnect logic; click browser refresh (`F5`) | UI automatically falls back to 2-second REST polling |
| **Redpanda Broker Unavailable** | Medium | Docker daemon unresponsive | Switch to internal synthetic replay mode;<br/>no Redpanda required for backtesting or simulated roundtrip | Execute standalone deterministic verification script |
| **No Internet / Network Outage** | Low | Alpaca market data fetch stalls | All demonstration data is strictly local (synthetic 1m bars in SQLite/Parquet) | System has zero external network dependencies |

---

## 3. Pre-Validated Deterministic Scripts (Offline Fallback)

If the dashboard UI experiences rendering or browser issues, the presenter can immediately run the verified command-line demonstration scripts. These scripts output colorized, formatted console verification tables in under 3 seconds:

### Fallback 1: Deterministic Roundtrip Trading (BUY $\rightarrow$ SELL)
```powershell
python scripts/verify_gd40_deterministic_roundtrip.py
```
**Output Demonstrated**:
- Complete event-by-event progression through 74 bars.
- Golden Cross at Bar 60 $\rightarrow$ Fill at Bar 61 for 16 NVDA @ \$135.0675.
- Death Cross at Bar 70 $\rightarrow$ Fill at Bar 71 for 16 NVDA @ \$74.9625.
- Full gross realized P&L (-\$961.68), fee accounting (-\$3.00), and final cash (\$99,035.32).
- Cash discrepancy: **\$0.0000** (`Accounting Check Balanced: True`).

### Fallback 2: Multi-Bot Sandbox Isolation & Backtesting
```powershell
python scripts/verify_gd40_multibot_and_backtest.py
```
**Output Demonstrated**:
- Creation of 3 isolated bot sandboxes (`demo_bot_alpha`, `demo_bot_beta`, `demo_bot_gamma`).
- Independent state transition: Pausing Alpha while Beta and Gamma continue running.
- Dual-variant backtest execution: MA Cross vs RSI.
- SHA-256 fingerprint generation and side-by-side comparison table.

---

## 4. Machine-Readable Evidence Fallback

If live execution is completely constrained by environmental issues, the presenter can open and present the pre-verified JSON evidence files located in `data/status/`:

1. `data/status/gd40_demo_evidence.json`: Full recorded audit trace of the 74-bar deterministic roundtrip trade with order intents, fills, and zero-cash-discrepancy reconciliation.
2. `data/status/gd40_release_evidence.json`: Full recorded audit trace of multi-bot sandbox isolation, backtest runner outputs, and comparison metrics.
3. `data/status/gd40_safety_evidence.json`: Complete audit records verifying all 11 safety invariants (`DRY_RUN`, `Gate CLOSED`, 0 broker write calls).
4. `data/status/gd40_acceptance.json`: Formal release candidate acceptance record signed off as `CONDITIONALLY_READY_FOR_DEMO`.
