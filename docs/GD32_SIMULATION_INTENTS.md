# GD32 — SIMULATION ORDER INTENT SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ32 — Portfolio & Risk Management Engine  
**Module:** `libs/bot/domain.py`, `libs/bot/intent_store.py`  
**Execution Status:** STRICTLY UNEXECUTED (Intent Record Only)  

---

## 1. Intent Role & Scope

`SimulationOrderIntent` represents a formal request for simulated order execution.

> [!IMPORTANT]
> In GĐ32, the intent is **strictly an intent record**. It:
> 1. Does NOT create a `SimulatedOrder`.
> 2. Does NOT execute a `SimulatedFill`.
> 3. Does NOT call Mock Broker or Alpaca Broker APIs.
> 4. Does NOT deduct portfolio cash as if filled.
>
> Execution and fill simulation are strictly deferred to **GĐ33 (Order Management & Simulation Broker Engine)**.

---

## 2. Intent Schema & Properties

```python
@dataclass
class SimulationOrderIntent:
    intent_id: str                      # Unique intent identifier: intent_<hex12>
    decision_id: str                    # Parent decision ID
    signal_id: str                      # Strategy signal ID
    bot_session_id: str                 # Associated bot session
    portfolio_id: str                   # Simulation portfolio ID
    symbol: str                         # Traded asset ticker (e.g. AAPL, BTC/USD)
    side: str                           # "BUY" or "SELL"
    order_type: str = "MARKET"          # "MARKET" or "LIMIT"
    proposed_quantity: float = 0.0      # Validated order size
    proposed_notional: Optional[float]  # Estimated order notional
    reference_price: float = 0.0        # Price used during risk evaluation
    limit_price: Optional[float] = None # Optional limit price
    risk_configuration_version: str     # Version of risk config used (e.g. "1.0.0")
    idempotency_key: str                # SHA-256 deduplication key
    created_at: datetime                # UTC creation timestamp
    environment: str = "SIMULATION"     # Mandatory SIMULATION tag
```

---

## 3. Idempotency Key Formulation

To guarantee zero duplicate intents during replays or network retries, `idempotency_key` is calculated deterministically:

$$\text{idempotency\_key} = \text{SHA256}(\text{decision\_id} + ":" + \text{signal\_id} + ":" + \text{symbol} + ":" + \text{side} + ":" + \text{proposed\_qty})$$

`IntentStore` indexes all recorded keys and suppresses duplicate intent submissions automatically.
