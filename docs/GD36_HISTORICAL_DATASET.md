# GĐ36 — HISTORICAL DATASET MANAGER & MANIFEST SPECIFICATION

**Module:** `libs/bot/backtesting/dataset.py`  
**Purpose:** Dataset sanitization, OHLCV validation, gap analysis, market session filtering, and immutable manifest hashing.

---

## 1. Overview

The `HistoricalDatasetManager` prepares and packages historical 1m OHLCV bars into immutable datasets identified by unique `DatasetManifest` artifacts.

```
Raw Historical Bars (JSONL / Fixtures)
       │
       ▼
1. Mathematical OHLCV Validation (High >= Low, etc.)
       │
       ▼
2. Market Session Hours Filtering (Stocks vs Crypto)
       │
       ▼
3. Deduplication & Revision Resolution (Latest revision wins)
       │
       ▼
4. Deterministic Chronological Sorting
       │
       ▼
5. SHA-256 Checksum Computation & Manifest Generation
```

---

## 2. Validation Rules

Every bar evaluated by `HistoricalDatasetManager.validate_ohlcv()` must satisfy:
1. Positive prices: $\text{open} > 0, \text{high} > 0, \text{low} > 0, \text{close} > 0$.
2. High/Low boundary: $\text{high} \ge \text{low}$.
3. High bounding: $\text{high} \ge \text{open}$ and $\text{high} \ge \text{close}$.
4. Low bounding: $\text{low} \le \text{open}$ and $\text{low} \le \text{close}$.
5. Non-negative volume: $\text{volume} \ge 0$.
6. Finality requirement: `is_final == True` for strategy evaluation.

Bars violating these invariants raise `InvalidBarDataError`.

---

## 3. Market Session Hours

Trading sessions are strictly filtered based on the asset class:
- **US Equities (STOCKS):**
  - Regular Trading Hours: Monday–Friday, 14:30 to 21:00 UTC (09:30 to 16:00 EST).
  - Weekends (Saturday, Sunday) and off-hours are rejected or filtered out when `enforce_session_hours=True`.
- **Cryptocurrencies (CRYPTO):**
  - Continuous 24/7/365 trading. Weekend and overnight bars are treated as normal market data.

---

## 4. Gap Detection

The `detect_gaps()` static method scans chronological series per symbol to identify missing bars without interpolating fictitious prices:
$$\Delta t = t_{i+1} - t_i > \Delta t_{\text{expected}}$$
If $\Delta t > 60\text{ seconds}$, a gap diagnostic record is generated:
```json
{
  "symbol": "NVDA",
  "gap_start": "2026-11-20T14:30:00Z",
  "gap_end": "2026-11-20T14:45:00Z",
  "gap_seconds": 900.0,
  "missing_bars_estimated": 14
}
```

---

## 5. Dataset Manifest Schema

Every sanitized dataset produces a `DatasetManifest`:

```python
@dataclass
class DatasetManifest:
    dataset_id: str
    version: str
    symbol_counts: Dict[str, int]
    total_bars: int
    start_time: str
    end_time: str
    timeframe: str
    checksum_sha256: str
    is_synthetic: bool
    created_at: str
    environment: str = "SIMULATION"
```

The `checksum_sha256` is computed by feeding the canonical JSON serialization of all bars sorted by `(event_time, symbol.upper(), bar_revision)`. Any change in price, timestamp, or volume alters the manifest checksum.
