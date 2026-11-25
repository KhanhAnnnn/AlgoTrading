# GD35 — Security & Safety Invariants Audit

**Stage:** GĐ35 — API & Dashboard Integration  
**Repository:** `D:\AlgoTrading`  
**Audit Date:** 2026-11-23  
**Status:** VERIFIED & COMPLIANT  

---

## 1. Safety Invariants Verification

| Invariant Requirement | Required Value | Audit Result | Evidence |
|---|---|---|---|
| **Trading Mode** | `DRY_RUN` | **PASS** | Verified in all API schemas, bot summaries, and test cases |
| **Paper Execution Gate** | `is_gate_open = False` | **PASS** | Verified in `AlpacaPaperGate.is_gate_open` |
| **Simulation Tagging** | `environment = "SIMULATION"` | **PASS** | Enforced across all models in `schemas.py` |
| **Live Broker Endpoints** | Zero exposed | **PASS** | `test_tc64` verified zero live order routes in app routes |
| **Alpaca API Write Calls** | 0 calls | **PASS** | No imports or calls to Alpaca submit, replace, or cancel |
| **Decoupling from V1** | Full isolation | **PASS** | V2 runs independently on `/api/v2/bots` and `/ws/v2/bots` |

---

## 2. Authentication & Access Control

1. **REST Endpoints**:
   - `verify_api_key` dependency guards all `/api/v2/bots` endpoints.
   - When `V2_API_KEY` is configured in environment, requests without matching `X-API-Key` or `token` header return `401 Unauthorized`.
   - In local developer sandbox mode (`V2_API_KEY` not set), requests default to simulation mode without exposing credentials.
2. **WebSocket Handshake**:
   - `websocket_bot_stream` and `websocket_global_bot_stream` validate `token` query parameter during connection handshake.
   - Unauthorized attempts receive `WS_1008_POLICY_VIOLATION` and are closed before any telemetry is dispatched.

---

## 3. Input Sanitization & Resilience

1. **Schema Validation**:
   - `CreateBotRequest` enforces strict field boundaries (positive initial cash, risk limits in `(0, 0.50]`, valid timeframes).
   - Extra fields in risk configurations are forbidden via `model_config = {"extra": "forbid"}`.
2. **Environment Boundary Enforcement**:
   - `submit_bar` strictly rejects any incoming payload with `environment != "SIMULATION"` with `400 Bad Request`.
3. **Information Disclosure Prevention**:
   - Malformed JSON payloads return standard `422 Unprocessable Entity` or `400 Bad Request` without leaking internal tracebacks.
