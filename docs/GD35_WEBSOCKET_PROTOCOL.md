# GD35 — WebSocket Streaming & Synchronization Protocol

**Stage:** GĐ35 — API & Dashboard Integration  
**Repository:** `D:\AlgoTrading`  
**Protocol Version:** `2.0`  
**Transport:** WebSocket (JSON over WS/WSS)  

---

## 1. Overview & Channels

AlgoTrading V2.0 provides two real-time streaming WebSocket endpoints managed by `BotWebSocketManager`:

1. **Session Stream:** `/ws/v2/bots/{session_id}`  
   Streams real-time events specific to a single bot session, with initial snapshot dispatch and sequence-buffered replay.
2. **Global Stream:** `/ws/v2/bots`  
   Streams events across all active bot sessions for multi-bot dashboard monitoring.

---

## 2. Event Framing & Wire Protocol

Every message pushed by the server is framed in standard JSON:

```json
{
  "seq_id": 42,
  "session_id": "session_a63f118adb44",
  "event_type": "BOT_LIFECYCLE_EVENT",
  "timestamp": "2026-11-23T16:14:31.552000+00:00",
  "payload": {
    "action": "START",
    "state": "RUNNING",
    "session_id": "session_a63f118adb44"
  },
  "environment": "SIMULATION"
}
```

### Event Types
- `SNAPSHOT`: Complete state snapshot sent immediately on client connection or upon explicit resync request.
- `BOT_LIFECYCLE_EVENT`: Dispatched on START, PAUSE, RESUME, STOP.
- `STRATEGY_SIGNAL_EVENT`: Dispatched when strategy engine evaluates indicators and generates a signal.
- `RISK_DECISION_EVENT`: Dispatched when risk engine approves or rejects an order intent.
- `ORDER_EVENT`: Dispatched when a simulated order is created, modified, or transitioned.
- `FILL_EVENT`: Dispatched upon simulated fill execution.
- `PORTFOLIO_UPDATE`: Dispatched when cash, equity, or positions change.
- `HEALTH_EVENT`: Dispatched on heartbeat, latency warning, or error.

---

## 3. Sequence IDs & Monotonicity Guarantee

Every session maintains an independent sequence counter:
$$S_{t+1} = S_t + 1, \quad S_0 = 0$$

- Sequence IDs are strictly monotonically increasing.
- Sequence numbers are assigned before entering the bounded ring buffer (capacity: 200 events).
- Clients utilize `seq_id` for local deduplication and gap detection.

---

## 4. Heartbeat Protocol (PING / PONG)

Clients periodically transmit heartbeats to verify connection liveness:

### Client Ping:
```json
{
  "action": "PING",
  "timestamp": 1700755200000
}
```

### Server Pong:
```json
{
  "type": "PONG",
  "timestamp": 1700755200000,
  "server_time": "2026-11-23T16:14:31.558000+00:00"
}
```

---

## 5. Resynchronization & Replay Mechanism

When a client reconnects or detects a sequence gap:
1. Client sends:
   ```json
   {
     "action": "RESYNC",
     "last_seq_id": 140
   }
   ```
2. Server checks ring buffer `buf`:
   - If $last\_seq\_id \ge \min(buf) - 1$: Server replays all missed events where $seq\_id > last\_seq\_id$.
   - If $last\_seq\_id < \min(buf) - 1$ (gap exceeds buffer depth): Server dispatches full `SNAPSHOT` to reset baseline state.
3. Client receives replayed events in sequential order and seamlessly updates state.
