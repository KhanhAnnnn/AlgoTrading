"""
continuous_price_producer.py — Production-Grade Continuous Alpaca Stock Prices Producer
Polls 1-minute OHLCV stock bars from Alpaca (IEX feed), enforces strict deduplication,
maintains persistent checkpoints, handles rate limits with exponential backoff,
respects market hours, and publishes to Redpanda topic 'stock-prices'.
"""
import os
import sys
import time
import json
import signal
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import psutil

from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from alpaca.data import StockHistoricalDataClient, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient

# Include libs in path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_config.keys import config

# Directories
DATA_DIR = os.path.join(BASE_DIR, 'data')
CHECKPOINT_DIR = os.path.join(DATA_DIR, 'checkpoints')
LOCK_DIR = os.path.join(DATA_DIR, 'locks')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

for d in [CHECKPOINT_DIR, LOCK_DIR, STATUS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

PID_FILE = os.path.join(LOCK_DIR, 'price_producer.pid')
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'price_checkpoint.json')
HEALTH_FILE = os.path.join(STATUS_DIR, 'price_producer_health.json')
LOG_FILE = os.path.join(LOGS_DIR, 'price_producer.log')

# Setup Logging with Rotation
logger = logging.getLogger('continuous-price-producer')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s (PID %(process)d): %(message)s')

# Clear existing handlers to prevent duplicates
logger.handlers.clear()

# Console Handler
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Rotating File Handler (5 MB, 3 backups)
fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)


class SingleInstanceLock:
    def __init__(self, pid_file: str):
        self.pid_file = pid_file

    def acquire(self):
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    content = f.read().strip()
                if content:
                    old_pid = int(content)
                    if psutil.pid_exists(old_pid):
                        proc = psutil.Process(old_pid)
                        if 'python' in proc.name().lower() and old_pid != os.getpid():
                            logger.error("Another Price Producer instance (PID %d) is already active.", old_pid)
                            sys.exit(1)
            except Exception:
                pass
        # Write current PID
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def release(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except Exception:
                pass


class ContinuousPriceProducer:
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        topic: str = 'stock-prices',
        poll_interval_sec: int = 60,
    ):
        self.symbols = [s.upper() for s in (symbols or ['NVDA', 'AAPL'])]
        self.topic = topic
        self.poll_interval_sec = poll_interval_sec
        self.running = False
        self.start_time = time.time()
        self.error_count = 0
        self.backoff_sec = 0

        self.key_id = config.get('key_id')
        self.secret_key = config.get('secret_key')

        # Redpanda brokers: check REDPANDA_BROKERS env first
        env_brokers = os.environ.get('REDPANDA_BROKERS')
        if env_brokers:
            self.brokers = [b.strip() for b in env_brokers.split(',') if b.strip()]
        else:
            self.brokers = config.get('redpanda_brokers', ['localhost:9092', 'localhost:9093'])

        if not self.key_id or not self.secret_key:
            logger.error("Alpaca credentials missing in environment/.env.")
            sys.exit(1)

        self.data_client = StockHistoricalDataClient(api_key=self.key_id, secret_key=self.secret_key)
        self.trading_client = TradingClient(api_key=self.key_id, secret_key=self.secret_key, paper=True)

        self.producer = KafkaProducer(
            bootstrap_servers=self.brokers,
            key_serializer=str.encode,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5,
            acks='all'
        )

        # Checkpoint state
        self.checkpoint = self._load_checkpoint()

    def _bootstrap_from_kafka_if_needed(self, initial_checkpoint: Dict[str, Any]):
        """Inspects Kafka to discover the latest ingested candle timestamps per symbol if checkpoint is empty."""
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=self.brokers,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                consumer_timeout_ms=3000
            )
            partitions = consumer.partitions_for_topic(self.topic)
            if not partitions:
                consumer.close()
                return
            tps = [TopicPartition(self.topic, p) for p in partitions]
            end_offsets = consumer.end_offsets(tps)
            for tp in tps:
                end = end_offsets.get(tp, 0)
                if end > 0:
                    consumer.assign([tp])
                    consumer.seek(tp, max(0, end - 3000))
                    for msg in consumer:
                        try:
                            val = json.loads(msg.value.decode('utf-8'))
                            sym = val.get('symbol')
                            ts = val.get('timestamp')
                            if sym in initial_checkpoint['symbols'] and ts:
                                ts_ms = int(ts if ts > 100000000000 else ts * 1000)
                                if ts_ms > initial_checkpoint['symbols'][sym]['last_candle_timestamp_ms']:
                                    initial_checkpoint['symbols'][sym]['last_candle_timestamp_ms'] = ts_ms
                                    initial_checkpoint['symbols'][sym]['last_candle_time_iso'] = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
                                    initial_checkpoint['symbols'][sym]['last_close'] = float(val.get('close', 0.0))
                        except Exception:
                            continue
            consumer.close()
            logger.info("Bootstrapped checkpoint from Kafka existing state: %s", json.dumps({s: initial_checkpoint['symbols'][s]['last_candle_time_iso'] for s in self.symbols}))
        except Exception as e:
            logger.warning("Could not bootstrap checkpoint from Kafka: %s", e)

    def _load_checkpoint(self) -> Dict[str, Any]:
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Loaded price checkpoint: %s", json.dumps({s: data.get('symbols', {}).get(s, {}).get('last_candle_time_iso') for s in self.symbols}))
                    return data
            except Exception as e:
                logger.warning("Failed to load checkpoint file: %s. Creating new state.", e)

        # Default fresh state
        initial = {
            'symbols': {},
            'producer_id': 'continuous-price-producer-v1',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        for sym in self.symbols:
            initial['symbols'][sym] = {
                'last_candle_timestamp_ms': 0,
                'last_candle_time_iso': None,
                'last_close': None,
                'total_bars_emitted': 0,
            }

        # Bootstrap from existing Kafka topic records if present
        self._bootstrap_from_kafka_if_needed(initial)
        self.checkpoint = initial
        self._save_checkpoint()
        return initial

    def _save_checkpoint(self):
        try:
            self.checkpoint['last_updated_at'] = datetime.now(timezone.utc).isoformat()
            temp_file = CHECKPOINT_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint, f, indent=2)
            os.replace(temp_file, CHECKPOINT_FILE)
        except Exception as e:
            logger.error("Failed to save price checkpoint: %s", e)

    def _update_health(self, status: str, market_open: bool, details: Optional[Dict[str, Any]] = None):
        try:
            health = {
                'status': status,
                'pid': os.getpid(),
                'uptime_sec': int(time.time() - self.start_time),
                'market_open': market_open,
                'symbols': {s: self.checkpoint['symbols'].get(s, {}) for s in self.symbols},
                'error_count': self.error_count,
                'current_backoff_sec': self.backoff_sec,
                'last_heartbeat': datetime.now(timezone.utc).isoformat(),
            }
            if details:
                health.update(details)
            temp_file = HEALTH_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(health, f, indent=2)
            os.replace(temp_file, HEALTH_FILE)
        except Exception as e:
            logger.debug("Failed to write health file: %s", e)

    def check_market_clock(self) -> Dict[str, Any]:
        """Queries Alpaca clock to know if market is open."""
        try:
            clock = self.trading_client.get_clock()
            return {
                'is_open': clock.is_open,
                'timestamp': clock.timestamp.isoformat() if clock.timestamp else None,
                'next_open': clock.next_open.isoformat() if clock.next_open else None,
                'next_close': clock.next_close.isoformat() if clock.next_close else None,
            }
        except Exception as e:
            logger.warning("Could not query Alpaca clock: %s. Assuming closed on weekend.", e)
            now = datetime.now(timezone.utc)
            is_weekend = now.weekday() >= 5
            return {
                'is_open': not is_weekend,
                'timestamp': now.isoformat(),
                'next_open': None,
                'next_close': None,
            }

    def fetch_and_publish_symbol(self, symbol: str, is_backfill: bool = False) -> int:
        """
        Fetches bars for symbol since last checkpoint timestamp and publishes strictly new bars.
        Returns number of newly published bars.
        """
        sym_state = self.checkpoint['symbols'].setdefault(symbol, {
            'last_candle_timestamp_ms': 0,
            'last_candle_time_iso': None,
            'last_close': None,
            'total_bars_emitted': 0,
        })
        last_ts_ms = sym_state.get('last_candle_timestamp_ms', 0)

        # 15-minute delayed IEX feed buffer
        end_date = datetime.now(timezone.utc) - timedelta(minutes=15)

        if last_ts_ms > 0:
            start_date = datetime.fromtimestamp(last_ts_ms / 1000.0, tz=timezone.utc) + timedelta(minutes=1)
        else:
            # First bootstrap: fetch past 5 days
            start_date = end_date - timedelta(days=5)

        if start_date >= end_date:
            # Already up to date
            return 0

        logger.info(
            "[%s] Polling Alpaca bars from %s to %s (IEX feed)...",
            symbol, start_date.strftime('%Y-%m-%d %H:%M:%S UTC'), end_date.strftime('%Y-%m-%d %H:%M:%S UTC')
        )

        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start_date,
            end=end_date,
            feed=DataFeed.IEX
        )

        try:
            bars = self.data_client.get_stock_bars(request_params)
            df = bars.df
            if df is None or df.empty:
                logger.debug("[%s] No new price bars returned.", symbol)
                return 0
        except Exception as exc:
            self.error_count += 1
            logger.error("[%s] Alpaca API error fetching bars: %s", symbol, exc)
            raise exc

        df = df.reset_index()
        records = json.loads(df.to_json(orient='records'))
        new_count = 0

        for record in records:
            record['provider'] = 'alpaca'
            ts_ms = int(record['timestamp'])

            # Strict Deduplication Check
            if ts_ms <= last_ts_ms:
                continue

            try:
                self.producer.send(
                    topic=self.topic,
                    key=symbol,
                    value=record,
                    timestamp_ms=ts_ms
                )
                last_ts_ms = ts_ms
                new_count += 1
                sym_state['last_candle_timestamp_ms'] = ts_ms
                sym_state['last_candle_time_iso'] = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
                sym_state['last_close'] = float(record['close'])
                sym_state['total_bars_emitted'] = sym_state.get('total_bars_emitted', 0) + 1
            except Exception as e:
                logger.error("[%s] Kafka emit failed: %s", symbol, e)
                raise e

        if new_count > 0:
            self.producer.flush(timeout=10)
            self._save_checkpoint()
            logger.info(
                "[%s] Successfully emitted %d new bars to topic '%s' (latest close: $%.2f, time: %s)",
                symbol, new_count, self.topic, sym_state['last_close'], sym_state['last_candle_time_iso']
            )

        return new_count

    def start(self):
        self.running = True
        logger.info("Starting Continuous Price Producer for symbols: %s", self.symbols)

        # Step 1: Initial Checkpoint / Backfill
        for sym in self.symbols:
            try:
                emitted = self.fetch_and_publish_symbol(sym, is_backfill=True)
                if emitted > 0:
                    logger.info("[%s] Initial backfill complete: %d bars.", sym, emitted)
                else:
                    logger.info("[%s] Up to date from checkpoint. No backfill needed.", sym)
            except Exception as e:
                logger.warning("[%s] Initial backfill encountered error: %s. Will retry in loop.", sym, e)

        # Step 2: Main Continuous Polling Loop
        fail_count = 0
        while self.running:
            try:
                clock_info = self.check_market_clock()
                is_open = clock_info['is_open']

                if not is_open:
                    self._update_health("IDLE_MARKET_CLOSED", market_open=False, details={'clock': clock_info})
                    logger.info("Market is currently CLOSED. Next open: %s. Sleeping %ds...", clock_info.get('next_open'), self.poll_interval_sec)
                    time.sleep(self.poll_interval_sec)
                    continue

                # Market is OPEN: Poll each symbol
                total_emitted = 0
                for sym in self.symbols:
                    if not self.running:
                        break
                    emitted = self.fetch_and_publish_symbol(sym)
                    total_emitted += emitted

                fail_count = 0
                self.backoff_sec = 0
                self._update_health("RUNNING", market_open=True, details={'last_emitted_batch': total_emitted})

                # Sleep until next minute bar
                time.sleep(self.poll_interval_sec)

            except Exception as e:
                fail_count += 1
                self.error_count += 1
                # Exponential backoff: 2s, 4s, 8s, 16s, 32s, max 60s
                self.backoff_sec = min(60, 2 ** min(fail_count, 6))
                self._update_health("BACKING_OFF", market_open=False, details={'last_error': str(e)})
                logger.warning("Producer error: %s. Backing off for %ds (retry #%d)...", e, self.backoff_sec, fail_count)
                time.sleep(self.backoff_sec)

    def stop(self):
        logger.info("Stopping Continuous Price Producer...")
        self.running = False
        try:
            self.producer.flush(timeout=5)
            self.producer.close(timeout=5)
        except Exception:
            pass
        self._save_checkpoint()
        self._update_health("STOPPED", market_open=False)
        logger.info("Continuous Price Producer cleanly terminated.")


def main():
    lock = SingleInstanceLock(PID_FILE)
    lock.acquire()

    producer = ContinuousPriceProducer(symbols=['NVDA', 'AAPL'], poll_interval_sec=60)

    def handle_signal(sig, frame):
        logger.info("Received termination signal (%d). Shutting down...", sig)
        producer.stop()
        lock.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        producer.start()
    finally:
        lock.release()


if __name__ == '__main__':
    main()
