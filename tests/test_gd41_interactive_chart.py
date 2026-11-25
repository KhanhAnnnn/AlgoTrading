"""
tests/test_gd41_interactive_chart.py — Acceptance Tests for GĐ41 Interactive Backtest Trade Chart
Covers TradingView chart API contract, indicator parity with Strategy Engine, anti-lookahead separation
between StrategySignal and SimulatedFill, 25+ fills scale test on multi-thousand real Alpaca 1m bars,
partial fills & closed-trade P&L ledger reconciliation, and DRY_RUN safety guarantees.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
LIBS_DIR = os.path.join(BASE_DIR, "libs")
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)
BACKEND_DIR = os.path.join(BASE_DIR, "trading-dashboard", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from libs.alpaca_paper_gate import paper_gate
from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.sma import SMAIndicator
from libs.bot.indicators.rsi import RSIIndicator
from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.runner import BacktestRunner
from libs.bot.backtesting.store import BacktestStore
from libs.bot.backtesting.dataset import HistoricalDatasetManager
from libs.bot.backtesting.trade_ledger import build_closed_trades_and_associations
from main import app


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


class TestGD41InteractiveTradeChart:
    """Acceptance test suite for Interactive Backtest Trade Chart & Explorer."""

    def test_tc01_chart_endpoint_real_alpaca_stocks(self, api_client):
        """Fetches real NVDA (IEX) full session, runs backtest, and verifies /chart payload."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T21:00:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "initial_simulated_cash": 100000.0,
            "warmup_bars_count": 50,
            "execution_config": {"strategy_params": {"fast_period": 10, "slow_period": 25}},
        }
        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201, res.text
        run_id = res.json()["run_id"]

        chart_res = api_client.get(f"/api/v2/backtests/{run_id}/chart")
        assert chart_res.status_code == 200, chart_res.text
        chart = chart_res.json()

        assert chart["run_id"] == run_id
        assert chart["environment"] == "SIMULATION"
        assert chart["trading_mode"] == "DRY_RUN"
        assert chart["paper_execution_gate"] == "CLOSED"

        # Provenance & real market data verification
        manifest = chart["dataset_manifest"]
        assert manifest is not None
        assert manifest["provider"] == "ALPACA"
        assert manifest["feed"] == "IEX"
        assert manifest["is_synthetic"] is False
        assert manifest["source_type"] == "REAL_HISTORICAL_MARKET_DATA"

        candles = chart["candles"]
        assert len(candles) >= 300  # Full US session ~390 1m bars
        warmup_times = {c["time"] for c in candles if c["is_warmup"]}
        assert len(warmup_times) == 50

        # Ensure zero fills occurred during warmup bars
        for fill in chart["fills"]:
            assert fill["fill_epoch"] not in warmup_times

        # Ensure portfolio transactions and indicators present
        assert len(chart["portfolio_transactions"]) >= 1
        assert "NVDA" in chart["indicators"]["series_by_symbol"]

    def test_tc02_indicators_parity_with_strategy_engine(self, api_client):
        """Verifies MA Fast, MA Slow, and RSI 14 match exact Strategy Engine indicator outputs."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T21:00:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "warmup_bars_count": 30,
            "execution_config": {"strategy_params": {"fast_period": 12, "slow_period": 26, "period": 14}},
        }
        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201
        run_id = res.json()["run_id"]

        chart = api_client.get(f"/api/v2/backtests/{run_id}/chart").json()
        candles = chart["candles"]
        series = chart["indicators"]["series_by_symbol"]["NVDA"]

        assert len(series["ma_fast"]) == len(candles)
        assert len(series["ma_slow"]) == len(candles)
        assert len(series["rsi"]) == len(candles)

        # Verify insufficient data bars emit None (not fabricated values)
        for i in range(11):
            assert series["ma_fast"][i]["value"] is None
        for i in range(25):
            assert series["ma_slow"][i]["value"] is None
        for i in range(14):
            assert series["rsi"][i]["value"] is None

        # Independent check using Strategy Engine's SMAIndicator & RSIIndicator
        sma_fast = SMAIndicator(period=12)
        sma_slow = SMAIndicator(period=26)
        rsi = RSIIndicator(period=14, method="SIMPLE_ROLLING")

        for idx, c in enumerate(candles):
            mde = MarketDataEvent(
                symbol="NVDA",
                event_time=datetime.fromisoformat(c["timestamp"]),
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c["volume"],
                is_final=True,
                environment="SIMULATION",
            )
            rf = sma_fast.update(mde)
            rs = sma_slow.update(mde)
            rr = rsi.update(mde)
            if rf.warmup_complete:
                assert series["ma_fast"][idx]["value"] == pytest.approx(rf.value, abs=1e-6)
            if rs.warmup_complete:
                assert series["ma_slow"][idx]["value"] == pytest.approx(rs.value, abs=1e-6)
            if rr.warmup_complete:
                assert series["rsi"][idx]["value"] == pytest.approx(rr.value, abs=1e-6)

        # Signal indicator_values must match chart indicator series at the signal bar
        fast_by_time = {pt["time"]: pt["value"] for pt in series["ma_fast"]}
        for sig in chart["signals"]:
            if sig.get("indicator_values") and "fast_sma" in sig["indicator_values"]:
                assert sig["indicator_values"]["fast_sma"] == pytest.approx(fast_by_time[sig["time"]], abs=1e-5)

    def test_tc03_execution_marker_vs_signal_marker_no_lookahead(self, api_client):
        """Verifies execution fills occur strictly on next eligible bar AFTER signal, with true execution price."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T21:00:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "warmup_bars_count": 20,
            "execution_config": {"strategy_params": {"fast_period": 5, "slow_period": 15}},
        }
        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201
        run_id = res.json()["run_id"]

        chart = api_client.get(f"/api/v2/backtests/{run_id}/chart").json()
        signals_by_id = {s["signal_id"]: s for s in chart["signals"]}
        candles_by_time = {c["time"]: c for c in chart["candles"]}

        assert len(chart["fills"]) >= 2
        for fill in chart["fills"]:
            assert fill["simulated_order_id"]
            assert fill["simulated_fill_id"]
            assert fill["signal_id"] in signals_by_id
            sig = signals_by_id[fill["signal_id"]]
            assert fill["strategy_reason"] == sig["reason"]
            # Anti-lookahead: fill bar must be strictly AFTER signal bar
            assert fill["fill_epoch"] > sig["time"]
            # Execution bar OHLC sanity: market fill uses next bar open + slippage (within realistic range)
            exec_bar = candles_by_time[fill["fill_epoch"]]
            assert exec_bar["low"] * 0.99 <= fill["fill_price"] <= exec_bar["high"] * 1.01

    def test_tc04_real_alpaca_multi_thousand_bars_25_plus_fills(self, api_client):
        """Acceptance #8: Multi-thousand real 1m Alpaca bars producing >= 25 fills displayed cleanly."""
        payload = {
            "symbol": "BTC/USD",
            "asset_class": "CRYPTO",
            "timeframe": "1m",
            "start_time": "2024-11-18T00:00:00Z",
            "end_time": "2024-11-21T00:00:00Z",
            "feed": "CRYPTO",
            "strategy_id": "MA_CROSS_1M",
            "initial_simulated_cash": 100000.0,
            "warmup_bars_count": 20,
            "execution_config": {"strategy_params": {"fast_period": 4, "slow_period": 12}},
        }
        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201, res.text
        run_id = res.json()["run_id"]

        chart = api_client.get(f"/api/v2/backtests/{run_id}/chart").json()
        assert len(chart["candles"]) >= 2500, f"Expected multi-thousand bars, got {len(chart['candles'])}"
        assert len(chart["fills"]) >= 25, f"Expected >= 25 fills for acceptance #8, got {len(chart['fills'])}"
        assert len(chart["closed_trades"]) >= 10

        # Consistency check: Chart fills == /trades endpoint == metrics total_fills
        trades_res = api_client.get(f"/api/v2/backtests/{run_id}/trades").json()
        assert len(chart["fills"]) == len(trades_res) == chart["metrics"]["total_fills"]

        # Closed trade gross_pnl reconciliation against portfolio realized_pnl
        sum_gross_pnl = sum(t["gross_pnl"] for t in chart["closed_trades"])
        assert sum_gross_pnl == pytest.approx(chart["metrics"]["realized_pnl"], abs=0.5)

    def test_tc05_partial_fills_and_same_timestamp_preservation(self, tmp_path):
        """Verifies multiple partial fills across consecutive bars & same-timestamp fills are never dropped."""
        # Create synthetic bars where bar volume is tight enough to trigger partial fills (max_participation=0.10)
        base = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        bars = []
        price = 100.0
        for i in range(60):
            t = base + timedelta(minutes=i)
            # Downtrend then sharp uptrend then downtrend to trigger MA crossover BUY then SELL
            if i < 20:
                price -= 0.4
            elif i < 40:
                price += 0.9
            else:
                price -= 1.0
            bars.append(MarketDataEvent(
                event_id=f"pf_{i}",
                event_time=t,
                ingest_time=t,
                symbol="NVDA",
                asset_class="STOCKS",
                timeframe="1m",
                open=price,
                high=price + 0.3,
                low=price - 0.3,
                close=price,
                volume=50.0,  # With 10% participation, max 5 shares/bar while ~20 shares ordered -> multi-bar partial fills!
                is_final=True,
                environment="SIMULATION",
            ))

        cfg = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
            warmup_bars_count=15,
            volume_participation_rate=0.10,
            execution_config={"strategy_params": {"fast_period": 4, "slow_period": 10}},
        )
        store = BacktestStore(base_dir=str(tmp_path / "backtests"))
        ds_mgr = HistoricalDatasetManager(base_dir=str(tmp_path / "datasets"))
        runner = BacktestRunner(config=cfg, store=store, dataset_manager=ds_mgr)
        result = runner.run(bars)

        # Should generate partial fills across bars without dropping any fill
        partial_fills = [f for f in result.fills if f.get("is_partial_fill")]
        assert len(result.fills) >= 2
        assert len(partial_fills) >= 1, "Expected partial fills under tight bar volume participation cap"

        # Test closed trade association with two fills sharing identical timestamp
        same_ts = "2026-11-20T15:00:00+00:00"
        same_ts_fills = [
            {"simulated_fill_id": "f_a", "simulated_order_id": "o_1", "symbol": "NVDA", "side": "BUY", "fill_qty": 10, "fill_price": 100.0, "fee": 0.5, "slippage": 0.0, "fill_time": same_ts},
            {"simulated_fill_id": "f_b", "simulated_order_id": "o_2", "symbol": "NVDA", "side": "BUY", "fill_qty": 10, "fill_price": 102.0, "fee": 0.5, "slippage": 0.0, "fill_time": same_ts},
            {"simulated_fill_id": "f_c", "simulated_order_id": "o_3", "symbol": "NVDA", "side": "SELL", "fill_qty": 20, "fill_price": 105.0, "fee": 1.0, "slippage": 0.0, "fill_time": "2026-11-20T15:05:00+00:00"},
        ]
        closed = build_closed_trades_and_associations(same_ts_fills)
        assert len(closed) == 1
        assert set(closed[0]["entry_fill_ids"]) == {"f_a", "f_b"}
        assert closed[0]["entry_price"] == pytest.approx(101.0, abs=1e-4)
        assert closed[0]["gross_pnl"] == pytest.approx(80.0, abs=1e-4)
        assert closed[0]["net_pnl"] == pytest.approx(78.0, abs=1e-4)

    def test_tc06_safety_and_synthetic_isolation(self, api_client):
        """Verifies DRY_RUN, closed PaperExecutionGate, and explicit synthetic labeling."""
        assert not paper_gate.is_gate_open
        assert paper_gate.mode in ("ALPACA_PAPER_READ_ONLY", "MOCK")

        syn_res = api_client.post("/api/v2/backtests", json={
            "strategy_id": "MA_CROSS_1M",
            "symbols": ["NVDA"],
            "synthetic_bars_count": 60,
            "warmup_bars_count": 15,
        })
        assert syn_res.status_code == 201
        syn_chart = api_client.get(f"/api/v2/backtests/{syn_res.json()['run_id']}/chart").json()
        assert syn_chart["dataset_manifest"]["is_synthetic"] is True
        assert syn_chart["data_source"] == "SYNTHETIC_FIXTURE"

    def test_tc07_timezone_est_edt_holiday_and_early_close(self):
        """Verifies EST/EDT automatic transitions, US holidays, 13:00 early closes, and Crypto 24/7."""
        # EST (November): 09:30 EST = 14:30 UTC, 16:00 EST = 21:00 UTC
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 11, 20, 14, 29, tzinfo=timezone.utc), "STOCKS") == "PRE_MARKET"
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc), "STOCKS") is True
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 11, 20, 20, 59, tzinfo=timezone.utc), "STOCKS") is True
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc), "STOCKS") == "AFTER_HOURS"
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc), "STOCKS") is False

        # EDT (July): 09:30 EDT = 13:30 UTC, 16:00 EDT = 20:00 UTC
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 7, 15, 13, 29, tzinfo=timezone.utc), "STOCKS") == "PRE_MARKET"
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 7, 15, 13, 30, tzinfo=timezone.utc), "STOCKS") is True
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 7, 15, 19, 59, tzinfo=timezone.utc), "STOCKS") is True
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc), "STOCKS") == "AFTER_HOURS"

        # US Market Holiday (Thanksgiving 2026-11-26) & Early Close (Black Friday 2026-11-27 13:00 EST = 18:00 UTC)
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc), "STOCKS") == "CLOSED"
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc), "STOCKS") is True
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc), "STOCKS") == "AFTER_HOURS"

        # Crypto 24/7 always open
        assert HistoricalDatasetManager.classify_market_session(datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc), "CRYPTO") == "CRYPTO_24_7"
        assert HistoricalDatasetManager.is_regular_trading_hours(datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc), "CRYPTO") is True

    def test_tc08_gap_classification_and_no_fabrication(self):
        """Verifies session-aware gap classification without fabricating missing OHLC candles."""
        from libs.bot.backtesting.trade_ledger import serialize_candles

        def make_bar(dt_val, px=180.0):
            return MarketDataEvent(
                event_id=f"g_{int(dt_val.timestamp())}",
                event_time=dt_val,
                ingest_time=dt_val,
                symbol="NVDA",
                asset_class="STOCKS",
                timeframe="1m",
                open=px,
                high=px,
                low=px,
                close=px,
                volume=100.0,
                is_final=True,
                environment="SIMULATION",
            )

        bars = [
            make_bar(datetime(2026, 11, 11, 21, 59, tzinfo=timezone.utc)),  # After-hours end
            make_bar(datetime(2026, 11, 12, 13, 8, tzinfo=timezone.utc)),   # Pre-market start (overnight gap)
            make_bar(datetime(2026, 11, 12, 13, 18, tzinfo=timezone.utc)),  # Extended-hours no-trade gap (10m)
            make_bar(datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)),   # RTH bar
            make_bar(datetime(2026, 11, 12, 15, 3, tzinfo=timezone.utc)),   # Missing 2 minutes inside RTH
        ]

        gaps = HistoricalDatasetManager.detect_gaps(bars, expected_step_minutes=1, asset_classes={"NVDA": "STOCKS"})
        summary = HistoricalDatasetManager.summarize_gaps(gaps)

        assert summary["non_trading_session"] >= 2  # Overnight (21:59->13:08) and transition across extended->RTH (>1h)
        assert summary["extended_hours_no_trade"] == 1  # 13:08 -> 13:18
        assert summary["rth_missing"] == 1  # 15:00 -> 15:03
        # Strictly zero fabricated candles inserted into serialized series
        serialized = serialize_candles(bars, warmup_count=0, asset_classes={"NVDA": "STOCKS"})
        assert len(serialized) == len(bars)
        assert [c["session"] for c in serialized] == ["AFTER_HOURS", "PRE_MARKET", "PRE_MARKET", "RTH", "RTH"]

    def test_tc09_zero_volume_and_flat_tiny_candles_preserved(self, tmp_path):
        """Verifies zero-volume and flat/tiny-body OHLC candles remain exact without mutation or crashes."""
        from libs.bot.backtesting.trade_ledger import serialize_candles, compute_strategy_indicators

        base = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        bars = []
        for i in range(60):
            t = base + timedelta(minutes=i)
            if i < 10:
                # Flat bar (O=H=L=C) with zero volume
                o = h = l = c = 180.25
                vol = 0.0
            elif i < 20:
                # Tiny-body bar (range = 0.01)
                o = 180.25
                h = 180.26
                l = 180.25
                c = 180.255
                vol = 100.0
            else:
                o = 180.0 + (i - 20) * 0.1
                h = o + 0.2
                l = o - 0.2
                c = o + 0.1
                vol = 2000.0
            bars.append(MarketDataEvent(
                event_id=f"zv_{i}",
                event_time=t,
                ingest_time=t,
                symbol="NVDA",
                asset_class="STOCKS",
                timeframe="1m",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vol,
                is_final=True,
                environment="SIMULATION",
            ))

        candles = serialize_candles(bars, warmup_count=20, asset_classes={"NVDA": "STOCKS"})
        assert candles[0]["open"] == candles[0]["high"] == candles[0]["low"] == candles[0]["close"] == 180.25
        assert candles[0]["volume"] == 0.0
        assert candles[12]["high"] == pytest.approx(180.26, abs=1e-6)

        ind = compute_strategy_indicators(bars, "MA_CROSS_1M", {"strategy_params": {"fast_period": 20, "slow_period": 50}})
        assert len(ind["series_by_symbol"]["NVDA"]["ma_fast"]) == 60
        assert ind["readiness_by_symbol"]["NVDA"]["ma_fast_ready_bar"] == 20
        assert ind["readiness_by_symbol"]["NVDA"]["ma_slow_ready_bar"] == 50

        cfg = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
            warmup_bars_count=20,
            market_session_policy="STRICT_HOURS",
            execution_config={"strategy_params": {"fast_period": 20, "slow_period": 50}},
        )
        runner = BacktestRunner(
            config=cfg,
            store=BacktestStore(base_dir=str(tmp_path / "bt")),
            dataset_manager=HistoricalDatasetManager(base_dir=str(tmp_path / "ds")),
        )
        res = runner.run(bars)
        assert len(res.bars) == 60
        assert res.bars[0]["volume"] == 0.0
        assert res.bars[0]["open"] == res.bars[0]["high"] == res.bars[0]["low"] == res.bars[0]["close"]

    def test_tc10_strict_hours_enforcement_and_warmup20_vs_ma50(self, tmp_path):
        """Verifies STRICT_HOURS filters extended hours and MA50 suppresses incomplete-indicator signals."""
        bars = []
        # 25 pre-market flat bars (14:05 - 14:29 UTC)
        pre_start = datetime(2026, 11, 20, 14, 5, tzinfo=timezone.utc)
        for i in range(25):
            t = pre_start + timedelta(minutes=i)
            bars.append(MarketDataEvent(
                event_id=f"pre_{i}", event_time=t, ingest_time=t,
                symbol="NVDA", asset_class="STOCKS", timeframe="1m",
                open=180.0, high=180.0, low=180.0, close=180.0, volume=100.0,
                is_final=True, environment="SIMULATION",
            ))

        # 80 RTH oscillating bars (14:30 - 15:49 UTC)
        rth_start = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
        px = 180.0
        for i in range(80):
            t = rth_start + timedelta(minutes=i)
            px += (0.6 if (i // 12) % 2 == 0 else -0.5)
            bars.append(MarketDataEvent(
                event_id=f"rth_{i}", event_time=t, ingest_time=t,
                symbol="NVDA", asset_class="STOCKS", timeframe="1m",
                open=px - 0.1, high=px + 0.3, low=px - 0.3, close=px, volume=15000.0,
                is_final=True, environment="SIMULATION",
            ))

        # 10 after-hours bars (21:00 - 21:09 UTC)
        aft_start = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)
        for i in range(10):
            t = aft_start + timedelta(minutes=i)
            bars.append(MarketDataEvent(
                event_id=f"aft_{i}", event_time=t, ingest_time=t,
                symbol="NVDA", asset_class="STOCKS", timeframe="1m",
                open=px, high=px, low=px, close=px, volume=50.0,
                is_final=True, environment="SIMULATION",
            ))

        # 1. STRICT_HOURS must retain only the 80 RTH bars
        cfg_strict = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
            warmup_bars_count=20,
            market_session_policy="STRICT_HOURS",
            execution_config={"strategy_params": {"fast_period": 20, "slow_period": 50}},
        )
        r_strict = BacktestRunner(
            config=cfg_strict,
            store=BacktestStore(base_dir=str(tmp_path / "bt_s")),
            dataset_manager=HistoricalDatasetManager(base_dir=str(tmp_path / "ds_s")),
        ).run(bars)
        assert len(r_strict.bars) == 80
        assert all(c["session"] == "RTH" for c in r_strict.bars)
        ma50_ready_epoch = r_strict.bars[49]["time"]  # 50th bar (index 49)
        for s in r_strict.signals:
            assert s["time"] >= ma50_ready_epoch, "Signal emitted before MA50 warmup completed!"
        for f in r_strict.fills:
            assert f["fill_epoch"] > ma50_ready_epoch, "Fill occurred before signal + next bar execution!"

        # 2. ALL_HOURS preserves all 115 bars with mixed sessions
        cfg_all = BacktestConfig(
            strategy_id="MA_CROSS_1M",
            symbols=["NVDA"],
            initial_simulated_cash=100000.0,
            warmup_bars_count=20,
            market_session_policy="ALL_HOURS",
            execution_config={"strategy_params": {"fast_period": 20, "slow_period": 50}},
        )
        r_all = BacktestRunner(
            config=cfg_all,
            store=BacktestStore(base_dir=str(tmp_path / "bt_a")),
            dataset_manager=HistoricalDatasetManager(base_dir=str(tmp_path / "ds_a")),
        ).run(bars)
        assert len(r_all.bars) == 115

    def test_tc11_chart_api_diagnostics_and_fill_mapping(self, api_client):
        """Verifies /chart returns window comparisons, gap_summary, readiness, and exact fill coordinates."""
        payload = {
            "symbol": "NVDA",
            "timeframe": "1m",
            "start_time": "2024-11-20T14:30:00Z",
            "end_time": "2024-11-20T21:00:00Z",
            "feed": "IEX",
            "strategy_id": "MA_CROSS_1M",
            "initial_simulated_cash": 100000.0,
            "warmup_bars_count": 20,
            "market_session_policy": "STRICT_HOURS",
            "execution_config": {"strategy_params": {"fast_period": 5, "slow_period": 15}},
        }
        res = api_client.post("/api/v2/backtests/from-alpaca", json=payload)
        assert res.status_code == 201, res.text
        chart = api_client.get(f"/api/v2/backtests/{res.json()['run_id']}/chart").json()

        assert chart["session_policy"] == "STRICT_HOURS"
        assert "session_counts" in chart and chart["session_counts"].get("RTH", 0) > 0
        assert chart["session_counts"].get("PRE_MARKET", 0) == 0
        assert chart["session_counts"].get("AFTER_HOURS", 0) == 0
        assert "gap_summary" in chart
        assert "requested_window" in chart and "actual_window" in chart
        assert chart["indicator_readiness"]["NVDA"]["ma_slow_ready_bar"] == 15

        bars_by_ep = {c["time"]: c for c in chart["candles"]}
        for fill in chart["fills"]:
            assert fill["fill_epoch"] in bars_by_ep
            bar = bars_by_ep[fill["fill_epoch"]]
            assert bar["is_warmup"] is False
            assert bar["low"] * 0.99 <= fill["fill_price"] <= bar["high"] * 1.01

    def test_tc12_supported_assets_registry_and_symbol_normalization(self, api_client):
        """Verifies authoritative asset registry endpoint and crypto alias normalization."""
        from libs.bot.backtesting.alpaca_client import AlpacaHistoricalClient

        assert AlpacaHistoricalClient.normalize_symbol("BTCUSD") == "BTC/USD"
        assert AlpacaHistoricalClient.normalize_symbol("btc-usd") == "BTC/USD"
        assert AlpacaHistoricalClient.normalize_symbol("ETH") == "ETH/USD"
        assert AlpacaHistoricalClient.normalize_symbol("SOLUSD") == "SOL/USD"
        assert AlpacaHistoricalClient.normalize_symbol("nvda") == "NVDA"
        assert AlpacaHistoricalClient.detect_asset_class("BTCUSD") == "CRYPTO"
        assert AlpacaHistoricalClient.detect_asset_class("MSFT") == "STOCKS"

        res = api_client.get("/api/v2/historical-data/symbols")
        assert res.status_code == 200
        body = res.json()
        stock_syms = {s["symbol"] for s in body["stocks"]}
        crypto_syms = {c["symbol"] for c in body["crypto"]}
        assert {"NVDA", "AAPL", "TSLA", "MSFT"}.issubset(stock_syms)
        assert {"BTC/USD", "ETH/USD", "SOL/USD"}.issubset(crypto_syms)

    def test_tc13_multi_asset_stocks_and_crypto_chart_parity(self, tmp_path):
        """Validates chronological sorting, session calendars, price precision, and indicator parity across all asset classes."""
        from libs.bot.backtesting.trade_ledger import compute_strategy_indicators

        test_specs = [
            ("NVDA", "STOCKS", 180.0, "MA_CROSS_1M", datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)),
            ("AAPL", "STOCKS", 230.0, "MA_CROSS_1M", datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)),
            ("TSLA", "STOCKS", 340.0, "MA_CROSS_1M", datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)),
            ("MSFT", "STOCKS", 420.0, "RSI_1M", datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)),
            ("BTC/USD", "CRYPTO", 65000.0, "MA_CROSS_1M", datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)),  # Saturday 24/7!
            ("ETH/USD", "CRYPTO", 1900.0, "MA_CROSS_1M", datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)),
            ("SOL/USD", "CRYPTO", 0.7425, "RSI_1M", datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)),  # Sub-dollar precision test
        ]

        for idx, (sym, ac, base_px, strat, t0) in enumerate(test_specs):
            bars = []
            px = base_px
            for i in range(70):
                t = t0 + timedelta(minutes=i)
                step = (0.008 if (i // 10) % 2 == 0 else -0.006) * base_px
                px = max(base_px * 0.5, px + step)
                bars.append(MarketDataEvent(
                    event_id=f"ma_{idx}_{i}",
                    event_time=t,
                    ingest_time=t,
                    symbol=sym,
                    asset_class=ac,
                    timeframe="1m",
                    open=round(px * 0.999, 6),
                    high=round(px * 1.002, 6),
                    low=round(px * 0.998, 6),
                    close=round(px, 6),
                    volume=0.0 if (ac == "CRYPTO" and i % 3 == 0) else 5000.0,
                    is_final=True,
                    environment="SIMULATION",
                ))

            exec_cfg = {"strategy_params": {"period": 14, "oversold": 30, "overbought": 70}} if strat == "RSI_1M" else {"strategy_params": {"fast_period": 10, "slow_period": 25}}
            cfg = BacktestConfig(
                strategy_id=strat,
                symbols=[sym],
                asset_classes={sym: ac},
                initial_simulated_cash=100000.0,
                warmup_bars_count=20,
                market_session_policy="STRICT_HOURS",  # Crypto MUST bypass stock hours even on Saturday!
                execution_config=exec_cfg,
            )
            res = BacktestRunner(
                config=cfg,
                store=BacktestStore(base_dir=str(tmp_path / f"bt_{idx}")),
                dataset_manager=HistoricalDatasetManager(base_dir=str(tmp_path / f"ds_{idx}")),
            ).run(bars)

            assert len(res.bars) == 70, f"{sym} lost bars under STRICT_HOURS={ac}"
            if ac == "CRYPTO":
                assert all(c["session"] == "CRYPTO_24_7" for c in res.bars)
            else:
                assert all(c["session"] == "RTH" for c in res.bars)

            ind = compute_strategy_indicators(bars, strat, exec_cfg)
            series = ind["series_by_symbol"][sym]
            assert len(series["ma_fast"]) == len(res.bars)
            assert len(series["rsi"]) == len(res.bars)
            for c, r_pt in zip(res.bars, series["rsi"]):
                assert c["time"] == r_pt["time"]


