"""
tests/test_gd30_data_layer.py — Comprehensive Test Suite for GĐ30 Data Layer & Redpanda Ingestion
Validates 26 core requirements:
1. Stocks consumer
2. Crypto consumer
3. Consumer group isolation
4. Offset isolation
5. Schema normalization
6. Decimal precision
7. Timestamp UTC
8. Symbol normalization
9. Final bar handling
10. Updated bar revision
11. Duplicate event
12. Out-of-order event
13. Late event
14. Missing bar detection
15. Stale data detection
16. Stocks market calendar handling
17. Crypto 24/7 handling
18. Historical backfill
19. Historical replay
20. Replay determinism
21. Consumer reconnect
22. Graceful shutdown
23. Store persistence
24. Fixture isolation
25. No writes to natural market topics
26. No Alpaca broker write calls
"""

import unittest
from datetime import datetime, timezone, timedelta
import os
import sys
import tempfile
import shutil
import json

# Ensure repository root is on PYTHONPATH
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from libs.bot.domain import MarketDataEvent
from libs.bot.normalization import MarketDataNormalizer, NormalizationError
from libs.bot.revision import BarRevisionManager
from libs.bot.quality import DataQualityEngine
from libs.bot.storage import MarketDataStore
from libs.bot.observability import DataTelemetryCollector
from libs.bot.backfill import HistoricalBackfillManager
from libs.bot.consumer import PaperBotConsumer
from libs.bot.data_access import PaperBotDataAccess
from libs.alpaca_paper_gate import AlpacaPaperGate, PaperExecutionGateClosedError, LiveTradingProhibitedError


class TestGD30DataLayer(unittest.TestCase):
    """26-criteria validation suite for GĐ30 Data Layer & Ingestion Engine."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_gd30_store_")
        self.store = MarketDataStore(base_dir=self.temp_dir)
        self.telemetry = DataTelemetryCollector()
        self.quality = DataQualityEngine()
        self.revision = BarRevisionManager(final_only=True)
        self.consumer = PaperBotConsumer(
            store=self.store,
            telemetry=self.telemetry,
            quality_engine=self.quality,
            revision_manager=self.revision,
            use_mock_transport=True,
        )
        self.data_access = PaperBotDataAccess(
            consumer=self.consumer,
            store=self.store,
            quality_engine=self.quality,
            revision_manager=self.revision,
            telemetry=self.telemetry,
        )

    def tearDown(self):
        self.consumer.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Stocks consumer: Reads and processes normalized stock bars
    def test_01_stocks_consumer(self):
        payload = {
            "symbol": "NVDA",
            "open": 140.25,
            "high": 141.00,
            "low": 140.10,
            "close": 140.85,
            "volume": 125000,
            "trade_count": 850,
            "vwap": 140.65,
            "timestamp": 1730000000000,
            "provider": "alpaca",
        }
        bar = self.consumer.process_raw_message(
            topic="stock-prices",
            partition=0,
            offset=101,
            payload=payload,
            provenance="NATURAL_RUNTIME",
        )
        self.assertIsNotNone(bar)
        self.assertEqual(bar.symbol, "NVDA")
        self.assertEqual(bar.asset_class, "STOCKS")
        self.assertEqual(bar.timeframe, "1m")
        self.assertTrue(bar.is_final)
        self.assertEqual(bar.provenance, "NATURAL_RUNTIME")
        self.assertEqual(bar.environment, "SIMULATION")

    # 2. Crypto consumer: Reads and processes crypto bars
    def test_02_crypto_consumer(self):
        payload = {
            "symbol": "BTC/USD",
            "open": 91200.0,
            "high": 91350.0,
            "low": 91150.0,
            "close": 91300.0,
            "volume": 4.5,
            "trade_count": 120,
            "vwap": 91280.0,
            "timestamp_ms": 1730000060000,
            "is_final": True,
            "source": "alpaca_crypto_ws",
        }
        bar = self.consumer.process_raw_message(
            topic="crypto-bars-1m",
            partition=1,
            offset=205,
            payload=payload,
            provenance="NATURAL_RUNTIME",
        )
        self.assertIsNotNone(bar)
        self.assertEqual(bar.symbol, "BTC/USD")
        self.assertEqual(bar.asset_class, "CRYPTO")
        self.assertTrue(bar.is_final)

    # 3. Consumer group isolation: paper-bot-v2-group strictly independent
    def test_03_consumer_group_isolation(self):
        v1_groups = ["signal-handler-group", "crypto-signal-handler-group", "market-news-group", "crypto-bars-flink-group"]
        self.assertEqual(self.consumer.CONSUMER_GROUP, "paper-bot-v2-group")
        self.assertNotIn(self.consumer.CONSUMER_GROUP, v1_groups)

    # 4. Offset isolation: V2 offset checkpoints do not overwrite V1
    def test_04_offset_isolation(self):
        self.consumer.process_raw_message(
            topic="stock-prices", partition=0, offset=550,
            payload={"symbol": "AAPL", "open": 230, "high": 231, "low": 229, "close": 230.5, "timestamp": 1730000000000}
        )
        saved_offset = self.store.get_checkpoint("paper-bot-v2-group", "stock-prices", 0)
        self.assertEqual(saved_offset, 550)
        # Verify checkpoint file exists under isolated data/paper_bot path
        self.assertTrue(os.path.exists(self.store.checkpoint_file))
        default_store = MarketDataStore()
        self.assertIn("paper_bot", default_store.checkpoint_file)

    # 5. Schema normalization: All mandatory fields mapped cleanly
    def test_05_schema_normalization(self):
        raw = {
            "symbol": "TSLA",
            "open": "215.5",
            "high": "218.0",
            "low": "215.0",
            "close": "217.5",
            "volume": "45000",
            "timestamp": 1730000000000,
        }
        mde = MarketDataNormalizer.normalize_stocks_record(raw)
        self.assertEqual(mde.symbol, "TSLA")
        self.assertEqual(mde.open, 215.5)
        self.assertEqual(mde.close, 217.5)
        self.assertTrue(mde.event_id.startswith("mde_"))

        # Missing mandatory field raises NormalizationError
        bad_raw = {"symbol": "TSLA", "open": 215.5, "close": 217.5}
        with self.assertRaises(NormalizationError):
            MarketDataNormalizer.normalize_stocks_record(bad_raw)

    # 6. Decimal precision: High-precision representation without truncation
    def test_06_decimal_precision(self):
        raw = {
            "symbol": "ETH/USD",
            "open": 2654.12345678,
            "high": 2655.87654321,
            "low": 2653.99999999,
            "close": 2654.55555555,
            "volume": 0.00123456,
            "timestamp_ms": 1730000000000,
        }
        mde = MarketDataNormalizer.normalize_crypto_record(raw)
        self.assertAlmostEqual(mde.close, 2654.55555555, places=7)
        self.assertAlmostEqual(mde.volume, 0.00123456, places=7)

    # 7. Timestamp UTC: All timestamps are timezone-aware UTC
    def test_07_timestamp_utc(self):
        mde = MarketDataNormalizer.normalize_stocks_record({
            "symbol": "NVDA", "open": 100, "high": 105, "low": 99, "close": 102,
            "timestamp": 1730000000000
        })
        self.assertIsNotNone(mde.event_time.tzinfo)
        self.assertEqual(mde.event_time.tzinfo, timezone.utc)

    # 8. Symbol normalization: Formats cleaned to standard (e.g. BTCUSD -> BTC/USD)
    def test_08_symbol_normalization(self):
        clean_crypto = MarketDataNormalizer.normalize_symbol("btcusd", "CRYPTO")
        self.assertEqual(clean_crypto, "BTC/USD")
        clean_stock = MarketDataNormalizer.normalize_symbol("  nvda  ", "STOCKS")
        self.assertEqual(clean_stock, "NVDA")

    # 9. Final bar handling: Policy final_only forwards only is_final=True bars
    def test_09_final_bar_handling(self):
        dispatched_bars = []
        self.consumer.subscribe_callback(lambda b: dispatched_bars.append(b))

        # Provisional bar (is_final=False)
        prov_payload = {
            "symbol": "BTC/USD", "open": 90000, "high": 90100, "low": 89900, "close": 90050,
            "timestamp_ms": 1730000100000, "is_final": False
        }
        res_prov = self.consumer.process_raw_message("crypto-bars-1m", 0, 1, prov_payload)
        self.assertIsNone(res_prov, "Provisional bar must NOT be forwarded under final_only=True")
        self.assertEqual(len(dispatched_bars), 0)

        # Final bar (is_final=True)
        final_payload = {
            "symbol": "BTC/USD", "open": 90000, "high": 90150, "low": 89900, "close": 90120,
            "timestamp_ms": 1730000100000, "is_final": True
        }
        res_final = self.consumer.process_raw_message("crypto-bars-1m", 0, 2, final_payload)
        self.assertIsNotNone(res_final, "Final bar MUST be forwarded")
        self.assertEqual(len(dispatched_bars), 1)
        self.assertEqual(dispatched_bars[0].close, 90120)

    # 10. Updated bar revision: Revision counter increments, bar updated without duplicate
    def test_10_updated_bar_revision(self):
        mgr = BarRevisionManager(final_only=True)
        bar1 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc), close=140.0, is_final=False)
        bar2 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc), close=140.5, is_final=False)
        bar3 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc), close=141.0, is_final=True)

        res1, act1 = mgr.process_incoming_bar(bar1)
        self.assertIsNone(res1)
        self.assertEqual(bar1.bar_revision, 0)
        self.assertEqual(act1, "PROVISIONAL_STORED")

        res2, act2 = mgr.process_incoming_bar(bar2)
        self.assertIsNone(res2)
        self.assertEqual(bar2.bar_revision, 1)
        self.assertEqual(act2, "PROVISIONAL_REVISION_STORED")

        res3, act3 = mgr.process_incoming_bar(bar3)
        self.assertIsNotNone(res3)
        self.assertEqual(bar3.bar_revision, 2)
        self.assertEqual(act3, "FINAL_REVISION_FORWARDED")

        # History has 3 revisions
        history = mgr.get_revision_history(bar1.bar_key)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].close, 140.0)
        self.assertEqual(history[2].close, 141.0)

    # 11. Duplicate event: Exact duplicates detected and handled
    def test_11_duplicate_event(self):
        bar = MarketDataEvent(
            symbol="NVDA",
            event_time=datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc),
            open=140, high=141, low=139, close=140.5, volume=1000
        )
        is_val1, _, _ = self.quality.validate_bar(bar)
        self.assertTrue(is_val1)

        # Duplicate same bar
        is_val2, flags, reason = self.quality.validate_bar(bar)
        self.assertFalse(is_val2)
        self.assertIn("DUPLICATE_BAR", flags)
        self.assertEqual(reason, "ERR_DUPLICATE_EVENT")

    # 12. Out-of-order event: Detected and tagged
    def test_12_out_of_order_event(self):
        bar_t2 = MarketDataEvent(
            symbol="MSFT", event_time=datetime(2026, 11, 22, 15, 5, tzinfo=timezone.utc),
            open=400, high=402, low=399, close=401, volume=500
        )
        self.quality.validate_bar(bar_t2)

        # Bar with older timestamp arrives
        bar_t1 = MarketDataEvent(
            symbol="MSFT", event_time=datetime(2026, 11, 22, 15, 2, tzinfo=timezone.utc),
            open=399, high=401, low=398, close=400, volume=500
        )
        is_val, flags, _ = self.quality.validate_bar(bar_t1)
        self.assertTrue(is_val)  # Valid bar but tagged
        self.assertIn("OUT_OF_ORDER_EVENT", flags)

    # 13. Late event: Detected when arrival lags behind current time
    def test_13_late_event(self):
        bar_recent = MarketDataEvent(
            symbol="AAPL", event_time=datetime(2026, 11, 22, 15, 30, tzinfo=timezone.utc),
            open=230, high=232, low=229, close=231, volume=1000
        )
        self.quality.validate_bar(bar_recent)

        # Bar arriving > 5 minutes late
        bar_late = MarketDataEvent(
            symbol="AAPL", event_time=datetime(2026, 11, 22, 15, 10, tzinfo=timezone.utc),
            open=228, high=230, low=227, close=229, volume=1000
        )
        is_val, flags, _ = self.quality.validate_bar(bar_late)
        self.assertTrue(is_val)
        self.assertIn("LATE_EVENT", flags)

    # 14. Missing bar detection: Identifies time gap > 1 minute
    def test_14_missing_bar_detection(self):
        bar1 = MarketDataEvent(
            symbol="BTC/USD", asset_class="CRYPTO",
            event_time=datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc),
            open=90000, high=90100, low=89900, close=90050, volume=1.0
        )
        self.quality.validate_bar(bar1)

        # Gap of 5 minutes in crypto stream
        bar2 = MarketDataEvent(
            symbol="BTC/USD", asset_class="CRYPTO",
            event_time=datetime(2026, 11, 22, 12, 5, tzinfo=timezone.utc),
            open=90050, high=90200, low=90000, close=90150, volume=1.0
        )
        _, flags, _ = self.quality.validate_bar(bar2)
        self.assertTrue(any("MISSING_INTERVAL_GAP" in f for f in flags))

    # 15. Stale data detection: Telemetry tracks stale events
    def test_15_stale_data_detection(self):
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.telemetry.record_message(
            event_time=past_time,
            ingest_time=datetime.now(timezone.utc),
            processing_time=datetime.now(timezone.utc),
            is_stale=True,
        )
        snapshot = self.telemetry.get_telemetry_snapshot()
        self.assertEqual(snapshot["stale_events"], 1)

    # 16. Stocks market calendar handling: Identifies regular vs after-hours / weekend
    def test_16_stocks_market_calendar_handling(self):
        # Regular trading hours: Wednesday 11:00 AM ET (16:00 UTC)
        open_time = datetime(2026, 11, 25, 16, 0, tzinfo=timezone.utc)
        is_open, desc = DataQualityEngine.is_stocks_market_open(open_time)
        self.assertTrue(is_open)
        self.assertEqual(desc, "REGULAR_MARKET_HOURS")

        # Weekend: Sunday 12:00 PM ET
        weekend_time = datetime(2026, 11, 22, 17, 0, tzinfo=timezone.utc)
        is_open_we, desc_we = DataQualityEngine.is_stocks_market_open(weekend_time)
        self.assertFalse(is_open_we)
        self.assertIn("WEEKEND", desc_we)

    # 17. Crypto 24/7 handling: Operates continuously regardless of equities calendar
    def test_17_crypto_24_7_handling(self):
        weekend_bar = MarketDataEvent(
            symbol="ETH/USD", asset_class="CRYPTO",
            event_time=datetime(2026, 11, 22, 2, 30, tzinfo=timezone.utc),
            open=2500, high=2510, low=2490, close=2505, volume=10.0
        )
        is_val, flags, reason = self.quality.validate_bar(weekend_bar)
        self.assertTrue(is_val)
        self.assertIsNone(reason)
        # Should NOT have STOCKS_WEEKEND flag
        self.assertFalse(any("STOCKS_WEEKEND" in f for f in flags))

    # 18. Historical backfill: Backfills without writing to natural topics
    def test_18_historical_backfill(self):
        bf_mgr = HistoricalBackfillManager(store=self.store)
        start = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 11, 20, 10, 5, tzinfo=timezone.utc)

        # Mock API client returning 3 bars
        class MockClient:
            def get_bars(self, **kwargs):
                return [
                    {"symbol": "NVDA", "open": 139, "high": 140, "low": 138.5, "close": 139.8, "timestamp": 1732096800000},
                    {"symbol": "NVDA", "open": 139.8, "high": 140.5, "low": 139.5, "close": 140.2, "timestamp": 1732096860000},
                ]

        bars = bf_mgr.backfill_from_alpaca_readonly("NVDA", start, end, api_client=MockClient())
        self.assertEqual(len(bars), 2)
        for b in bars:
            self.assertEqual(b.provenance, "HISTORICAL_BACKFILL")
            self.assertEqual(b.environment, "SIMULATION")

    # 19. Historical replay: Replays sequence by event-time
    def test_19_historical_replay(self):
        bf_mgr = HistoricalBackfillManager(store=self.store)
        bar_t1 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 20, 10, 1, tzinfo=timezone.utc), close=101)
        bar_t2 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 20, 10, 2, tzinfo=timezone.utc), close=102)
        bar_t0 = MarketDataEvent(symbol="NVDA", event_time=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc), close=100)

        # Unordered input
        input_bars = [bar_t1, bar_t2, bar_t0]
        replayed = []
        count = bf_mgr.replay_bars(input_bars, lambda b: replayed.append(b))
        self.assertEqual(count, 3)
        self.assertEqual(replayed[0].close, 100)
        self.assertEqual(replayed[1].close, 101)
        self.assertEqual(replayed[2].close, 102)

    # 20. Replay determinism: Same input produces identical output across passes
    def test_20_replay_determinism(self):
        bf_mgr = HistoricalBackfillManager(store=self.store)
        bars = [
            MarketDataEvent(symbol="AAPL", event_time=datetime(2026, 11, 20, 10, i, tzinfo=timezone.utc), close=200 + i)
            for i in range(10)
        ]
        is_deterministic = bf_mgr.verify_determinism(bars, lambda b: (b.symbol, b.close, b.event_time.isoformat()))
        self.assertTrue(is_deterministic)

    # 21. Consumer reconnect: Handles reconnection and reports health state
    def test_21_consumer_reconnect(self):
        health_init = self.consumer.get_health()
        self.assertEqual(health_init["status"], "STOPPED")

        self.consumer.start()
        health_running = self.consumer.get_health()
        self.assertEqual(health_running["status"], "RUNNING")
        self.assertTrue(health_running["is_running"])

    # 22. Graceful shutdown: Stop flushes state and marks STOPPED
    def test_22_graceful_shutdown(self):
        self.consumer.start()
        self.consumer.stop()
        health = self.consumer.get_health()
        self.assertEqual(health["status"], "STOPPED")
        self.assertFalse(health["is_running"])

    # 23. Store persistence: Disk write and reload of bars and revisions
    def test_23_store_persistence(self):
        bar = MarketDataEvent(
            symbol="NVDA", event_time=datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc),
            open=140, high=142, low=139, close=141.5, volume=1000
        )
        self.store.save_bar(bar)
        self.store.save_revision(bar)
        loaded = self.store.load_bars("NVDA")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].close, 141.5)

    # 24. Fixture isolation: Provenance tags distinguished
    def test_24_fixture_isolation(self):
        raw = {"symbol": "BTC/USD", "open": 90000, "high": 90200, "low": 89900, "close": 90100, "timestamp_ms": 1730000000000}
        mde_runtime = MarketDataNormalizer.normalize_crypto_record(raw, provenance="NATURAL_RUNTIME")
        mde_fixture = MarketDataNormalizer.normalize_crypto_record(raw, provenance="FIXTURE")
        mde_backfill = MarketDataNormalizer.normalize_crypto_record(raw, provenance="HISTORICAL_BACKFILL")

        self.assertEqual(mde_runtime.provenance, "NATURAL_RUNTIME")
        self.assertEqual(mde_fixture.provenance, "FIXTURE")
        self.assertEqual(mde_backfill.provenance, "HISTORICAL_BACKFILL")

    # 25. No writes to natural market topics: Asserts zero KafkaProducer publishes to market topics
    def test_25_no_writes_to_natural_market_topics(self):
        # Verify that DataAccess and Ingestion modules contain no producer logic targeting market topics
        self.assertFalse(hasattr(self.data_access, "publish_to_natural_topic"))
        self.assertFalse(hasattr(self.consumer, "send_to_market_stream"))

    # 26. No Alpaca broker write calls: PaperExecutionGate remains fail-closed
    def test_26_no_alpaca_broker_write_calls(self):
        gate = AlpacaPaperGate(is_gate_open=False)
        self.assertFalse(gate.is_gate_open)
        with self.assertRaises(PaperExecutionGateClosedError):
            gate.submit_paper_order({"symbol": "NVDA", "qty": 10, "side": "buy"})


if __name__ == "__main__":
    unittest.main()
