# GD34 — CHECKPOINT & CRASH RECOVERY

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Modules:** `libs/bot/orchestration/checkpoint.py`, `libs/bot/orchestration/recovery.py`  

---

## 1. Checkpoint Architecture

A checkpoint represents a point-in-time, mathematically verifiable snapshot of a running bot session. Checkpoints are persisted atomically (write to temporary file, then atomic rename) to avoid corruption during unexpected process termination.

### Storage Location:
`data/paper_bot/checkpoints/checkpoint_<session_id>.json`

### Checkpoint Fields:
- `checkpoint_id`: Unique identifier (`cp_<hex>`).
- `bot_session_id`: Correlated session ID.
- `consumer_group`: Assigned Redpanda group (`paper-bot-v2-group`).
- `partition_offsets`: Current offsets across market data partitions.
- `last_processed_event_id`: ID of the most recent processed `MarketDataEvent`.
- `last_processed_bar_key`: Unique key of the most recent processed bar (`symbol:1m:iso_time`).
- `portfolio_snapshot_id`: Pointer to the immutable portfolio snapshot.
- `reconciliation_status`: State of the ledger (`BALANCED`).
- `configuration_hash`: SHA-256 hash of the operational `RiskConfig`.
- `timestamp`: UTC creation timestamp.
- `checksum`: Cryptographic SHA-256 integrity hash.
- `environment`: Strictly `"SIMULATION"`.

---

## 2. Integrity Hashing & Anti-Tampering

Every checkpoint contains a 64-character SHA-256 checksum computed across core identity fields:
$$\text{Checksum} = \text{SHA256}(\text{cp\_id} : \text{session\_id} : \text{consumer\_group} : \text{last\_bar\_key} : \text{snapshot\_id} : \text{config\_hash} : \text{status})$$

Upon loading (`load_checkpoint`):
1. The checksum is recomputed from the persisted payload.
2. If the persisted checksum does not match the computed checksum, a `ValueError("Checkpoint integrity violation")` is immediately raised, preventing execution on corrupted or tampered state.

---

## 3. Crash Recovery Procedure (`BotRecoveryManager`)

When recovering a bot after an ungraceful shutdown or restart:
1. **Session Rehydration:** Reads session metadata from `SessionStore`.
2. **Checkpoint Verification:** Loads and validates the checkpoint integrity hash.
3. **Configuration Drift Guard:** Compares the checkpoint configuration hash against the current `RiskConfig` hash. If a parameter was altered while the bot was offline, recovery is aborted with `Configuration hash mismatch`.
4. **Portfolio Rehydration:** Restores positions, cash balances, and reserved funds from `PortfolioStore`.
5. **Order & Fill Restoration:** Rehydrates active orders and executed fills from disk stores.
6. **Reconciliation Audit:** Verifies the three-way balance between cash, positions, and ledger before resuming the event loop.
