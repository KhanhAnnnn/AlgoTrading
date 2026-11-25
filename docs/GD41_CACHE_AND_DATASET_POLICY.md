# GĐ41 — CACHE AND DATASET POLICY

## 1. Storage Layout & Directory Structure
Datasets are versioned and stored under `data/paper_bot/datasets/{dataset_id}/`:

```
data/paper_bot/datasets/
├── ds_alpaca_NVDA_ce781c3b/
│   ├── manifest.json       <-- Immutable metadata & SHA-256 checksum
│   ├── bars.jsonl          <-- Chronologically ordered 1m OHLCV bars
│   └── ds_alpaca_NVDA.csv  <-- Generated on-demand for CSV export
├── ds_alpaca_BTC_USD_eb653ef3/
│   ├── manifest.json
│   └── bars.jsonl
```

---

## 2. Cache Invalidation & Lookup Policy
- **Deterministic Keying**: A cached dataset matches a request when:
  $$\text{Symbol}_{\text{req}} = \text{Symbol}_{\text{cached}} \land \text{Timeframe}_{\text{req}} = \text{Timeframe}_{\text{cached}} \land \text{Feed}_{\text{req}} = \text{Feed}_{\text{cached}} \land [T_{\text{start, req}}, T_{\text{end, req}}] \subseteq [T_{\text{start, cached}}, T_{\text{end, cached}}]$$
- **Force Refresh**: When `force_refresh=true`, the local cache is bypassed, a fresh query is sent to Alpaca, and a new dataset snapshot is created with a unique UUID.
- **Pinning Invariance**: Previous backtest runs pin their specific `dataset_id`. Updating or adding new datasets never mutates or overwrites datasets referenced by completed historical backtest runs.
- **V1 Independence**: V1 legacy cache and test fixtures remain strictly untouched.
