# GD32 — SIMULATION RISK ENGINE SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ32 — Portfolio & Risk Management Engine  
**Module:** `libs/bot/risk/limits.py`  
**Configuration Schema:** `libs/bot/risk/config.py`  

---

## 1. Overview

The Simulation Risk Engine enforces multi-tiered pre-trade and continuous risk boundaries on incoming `StrategySignal` inputs before any order intent can be generated.

---

## 2. Guard Categories & Reason Codes

### Group A: Position Limits
| Parameter | Default Value | Description | Breach Reason Code |
| :--- | :--- | :--- | :--- |
| `max_position_notional` | $\$25,000.00$ | Maximum USD value for any single position | `EXCEEDS_MAX_POSITION_NOTIONAL` |
| `max_position_qty` | $10,000.0$ | Maximum asset unit quantity for any position | `EXCEEDS_MAX_POSITION_QTY` |
| `max_symbol_exposure_pct` | $30.0\%$ | Max percentage of total portfolio equity in one symbol | `EXCEEDS_SYMBOL_EXPOSURE_LIMIT` |
| `max_portfolio_exposure_pct`| $100.0\%$ | Max gross exposure across all open positions | `EXCEEDS_PORTFOLIO_EXPOSURE_LIMIT` |

### Group B: Cash & Exposure Checks
| Check | Condition | Breach Reason Code |
| :--- | :--- | :--- |
| **Available Cash** | $\text{ProposedNotional} \le \text{AvailableCash}$ | `INSUFFICIENT_SIMULATED_CASH` |
| **Reserved Cash** | $\text{AvailableCash} = \text{Cash} - \text{ReservedCash}$ | `INSUFFICIENT_SIMULATED_CASH` |
| **Duplicate Intent** | Same symbol & direction with identical intent hash | `DUPLICATE_INTENT_SUPPRESSED` |

### Group C: Portfolio Guards
| Parameter | Default Value | Description | Breach Reason Code |
| :--- | :--- | :--- | :--- |
| `max_concurrent_positions` | $5$ | Max open active positions simultaneously | `MAX_CONCURRENT_POSITIONS_REACHED` |
| `daily_loss_limit_pct` | $5.0\%$ | Maximum allowed realized + unrealized daily loss | `DAILY_LOSS_LIMIT_BREACHED` |
| `max_drawdown_pct` | $10.0\%$ | Peak-to-trough equity drop threshold | `DRAWDOWN_LIMIT_BREACHED` |

### Group D: Signal Guards
| Guard | Condition | Breach Reason Code |
| :--- | :--- | :--- |
| **Environment Tag** | `signal.environment == "SIMULATION"` | `NON_SIMULATION_ENVIRONMENT` |
| **Actionable Signal** | `signal.signal_type in {"BUY", "SELL"}` | `UNSUPPORTED_SIGNAL_TYPE_<TYPE>` |
| **Deduplication** | Unique `signal_id` check against session memory | `DUPLICATE_SIGNAL` |
| **Strategy Version** | `signal.strategy_version in whitelist` | `INCOMPATIBLE_STRATEGY_VERSION` |
| **Source Bar Finality** | `source_bar.is_final == True` | `UNFINALIZED_SOURCE_BAR` |
| **Bar Revision** | `source_bar.bar_revision == signal.source_bar_revision` | `SOURCE_BAR_REVISION_MISMATCH` |
| **Price Freshness** | Age $\le 300$ seconds and price $> 0$ | `STALE_REFERENCE_PRICE` / `INVALID_REFERENCE_PRICE` |
| **Short Selling** | `allow_short == False` requires existing position | `NO_EXISTING_POSITION_TO_SELL` |
