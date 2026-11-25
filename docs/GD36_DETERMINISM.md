# GĐ36 — DETERMINISM & REPRODUCIBILITY VERIFICATION

**Modules:** `libs/bot/backtesting/results.py`, `libs/bot/backtesting/config.py`  
**Purpose:** Cryptographic audit trail, invariant configuration hashing, and economic state equivalence verification.

---

## 1. Overview

In quantitative trading, backtesting results that cannot be independently reproduced across separate machine executions are unreliable. GĐ36 implements **Strict Bit-Level Determinism** for all simulation outcomes.

---

## 2. Configuration Hashing (`compute_config_hash`)

Every `BacktestConfig` produces a deterministic SHA-256 hash across all trading parameters:
- Strategy ID and version
- Sorted symbol list
- Timeframe
- Start and end time limits
- Initial capital
- Fee model and parameters
- Slippage model and parameters
- Volume participation cap
- Market session policy
- Warmup bar count
- Seed parameter
- Risk configuration hash

Transient runtime parameters (such as `backtest_run_id` or host timestamps) are explicitly omitted from the configuration hash.

---

## 3. Deterministic Economic Fingerprint

The `compute_deterministic_fingerprint()` method on `BacktestResult` computes an invariant SHA-256 hash across the final economic and ledger state:

```python
economic_state = {
    "strategy_id": self.config.strategy_id,
    "strategy_version": self.config.strategy_version,
    "symbols": sorted(self.config.symbols),
    "dataset_checksum": self.manifest.checksum_sha256 if self.manifest else "",
    "final_equity": round(float(m.get("final_equity", 0.0)), 2),
    "net_pnl": round(float(m.get("net_pnl", 0.0)), 2),
    "realized_pnl": round(float(m.get("realized_pnl", 0.0)), 2),
    "unrealized_pnl": round(float(m.get("unrealized_pnl", 0.0)), 2),
    "net_return_pct": round(float(m.get("net_return_pct", 0.0)), 4),
    "total_fees": round(float(m.get("total_fees", 0.0)), 2),
    "total_slippage": round(float(m.get("total_slippage", 0.0)), 2),
    "total_orders": int(m.get("total_orders", 0)),
    "filled_orders": int(m.get("filled_orders", 0)),
    "total_fills": int(m.get("total_fills", 0)),
    "total_trades": int(m.get("total_trades", 0)),
    "positions": sorted([...], key=lambda x: x["symbol"]),
}
```

### Properties
1. **Identical Replay Invariant:** Running the backtest twice on the same dataset with identical configuration produces identical SHA-256 fingerprints:
   $$\text{FP}(\text{Run}_1) \equiv \text{FP}(\text{Run}_2)$$
2. **Provenance Protection:** Changing a single bar's price in the dataset alters `dataset_checksum`, resulting in a different fingerprint.
3. **Auditability:** Independent reviewers can verify economic equivalence by running `res1.compare(res2)`.
