# Real-Time Algorithmic Trading Visualization Dashboard

A professional dark quant terminal dashboard built with **React 19 + TypeScript + Vite + TradingView Lightweight Charts** and **FastAPI + Kafka + WebSocket**.

## Architecture Overview

- **Frontend (`frontend/`)**:
  - TradingView Lightweight Charts for Candlestick & Volume.
  - SMA 20 (Cyan) and SMA 50 (Orange) indicators with data sufficiency validation.
  - Interactive BUY (green) and SELL (red) signal markers at exact event timestamps.
  - Market News Sentiment Panel with VADER compound score filtering.
  - Alpaca Paper Trading portfolio monitoring (strictly read-only).
  - Pipeline stream monitor (Redpanda Kafka, Flink SQL, topic message counts).
  - Historical Replay mode (Play/Pause, 1x/5x/10x/30x speeds, timeline scrubber).
- **Backend (`backend/`)**:
  - FastAPI web server running on port `8005`.
  - Kafka consumer service with dynamic session group ID for automatic full historical catch-up.
  - Real-time WebSocket (`/ws/live`) with async fan-out broadcast.
  - Timeframe aggregator (1m, 5m, 15m, 1h).
  - Alpaca Paper Trading read-only client (`/v2/account`, `/v2/positions`, `/v2/orders`).
- **Tests (`tests/`)**:
  - Full automated test suite (T01 - T16) verifying rendering, Kafka ingestion, candle sorting, deduplication, SMA accuracy, signal placement, news sentiment, Alpaca integration, and container health.

## Quick Start

```powershell
# From repository root D:\AlgoTrading:
.\run-dashboard.ps1
```

Access the terminal in your browser at `http://localhost:5173`.
Backend API docs available at `http://localhost:8005/docs`.

## Running Tests

```powershell
.\.venv\Scripts\pytest.exe trading-dashboard\tests\test_t01_t16.py -v
```
