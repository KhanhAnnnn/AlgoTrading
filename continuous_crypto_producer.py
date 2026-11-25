"""
continuous_crypto_producer.py — 24/7 Production Continuous Crypto Market Data & News Streaming
Streams real-time trades, minute bars, and updated bars for BTC/USD and ETH/USD via Alpaca Crypto WebSocket,
polls financial news with VADER sentiment, backfills missed bars, enforces strict deduplication,
maintains persistent checkpoints, and publishes to Redpanda topics:
- crypto-trades
- crypto-bars-1m
- crypto-news
"""
import os
import sys
import time
import json
import signal
import logging
import asyncio
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Set, Optional
import psutil
import requests
import websockets
from kafka import KafkaProducer, KafkaConsumer, TopicPartition
import nltk

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon', quiet=True)

from nltk.sentiment.vader import SentimentIntensityAnalyzer as SIA
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

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

PID_FILE = os.path.join(LOCK_DIR, 'crypto_producer.pid')
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'crypto_bars_checkpoint.json')
NEWS_CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'crypto_news_checkpoint.json')
HEALTH_FILE = os.path.join(STATUS_DIR, 'crypto_producer_health.json')
LOG_FILE = os.path.join(LOGS_DIR, 'crypto_producer.log')

# Logging
logger = logging.getLogger('continuous-crypto-producer')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s (PID %(process)d): %(message)s')

logger.handlers.clear()
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)

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
                    if psutil.pid_exists(old_pid) and old_pid != os.getpid():
                        proc = psutil.Process(old_pid)
                        if 'python' in proc.name().lower():
                            logger.error("Another Crypto Producer instance (PID %d) is already active.", old_pid)
                            sys.exit(1)
            except Exception:
                pass
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def release(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except Exception:
                pass


class ContinuousCryptoProducer:
    WS_URL = "wss://stream.data.alpaca.markets/v1beta3/crypto/us"

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        bootstrap_historical_hours: int = 12
    ):
        self.symbols = [s.upper() for s in (symbols or ['BTC/USD', 'ETH/USD'])]
        self.bootstrap_historical_hours = bootstrap_historical_hours
        self.running = False
        self.start_time = time.time()
        self.error_count = 0
        self.backoff_sec = 0

        self.key_id = config.get('key_id')
        self.secret_key = config.get('secret_key')

        env_brokers = os.environ.get('REDPANDA_BROKERS')
        if env_brokers:
            self.brokers = [b.strip() for b in env_brokers.split(',') if b.strip()]
        else:
            self.brokers = config.get('redpanda_brokers', ['localhost:9092', 'localhost:9093'])

        if not self.key_id or not self.secret_key:
            logger.error("Alpaca credentials missing in environment/.env.")
            sys.exit(1)

        self.sia = SIA()
        self.hist_client = CryptoHistoricalDataClient(self.key_id, self.secret_key)

        self.producer = KafkaProducer(
            bootstrap_servers=self.brokers,
            key_serializer=str.encode,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5,
            acks='all'
        )

        # Telemetry metrics
        self.metrics = {
            'trades_emitted': 0,
            'bars_emitted': 0,
            'updated_bars_emitted': 0,
            'news_emitted': 0,
            'last_trade_time': {},
            'last_bar_time': {},
        }
        for s in self.symbols:
            self.metrics['last_trade_time'][s] = None
            self.metrics['last_bar_time'][s] = None

        self.checkpoint = self._load_checkpoint()
        self.seen_news_ids: Set[Any] = self._load_news_checkpoint()

    def _load_checkpoint(self) -> Dict[str, Any]:
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Loaded crypto bars checkpoint: %s", json.dumps({s: data.get('symbols', {}).get(s, {}).get('last_bar_time_iso') for s in self.symbols}))
                    return data
            except Exception as e:
                logger.warning("Failed to load crypto checkpoint: %s. Rebuilding.", e)

        initial = {
            'symbols': {},
            'producer_id': 'continuous-crypto-producer-v1',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        for sym in self.symbols:
            initial['symbols'][sym] = {
                'last_bar_timestamp_ms': 0,
                'last_bar_time_iso': None,
                'last_close': None,
                'total_bars_emitted': 0,
            }
        return initial

    def _save_checkpoint(self):
        try:
            self.checkpoint['last_updated_at'] = datetime.now(timezone.utc).isoformat()
            temp_file = CHECKPOINT_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint, f, indent=2)
            os.replace(temp_file, CHECKPOINT_FILE)
        except Exception as e:
            logger.error("Failed to save crypto bars checkpoint: %s", e)

    def _load_news_checkpoint(self) -> Set[Any]:
        if os.path.exists(NEWS_CHECKPOINT_FILE):
            try:
                with open(NEWS_CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('seen_ids', []))
            except Exception:
                pass
        return set()

    def _save_news_checkpoint(self):
        try:
            temp_file = NEWS_CHECKPOINT_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'seen_ids': list(self.seen_news_ids)[-2000:],
                    'last_updated_at': datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
            os.replace(temp_file, NEWS_CHECKPOINT_FILE)
        except Exception as e:
            logger.error("Failed to save crypto news checkpoint: %s", e)

    def _update_health(self, status: str, details: Optional[Dict[str, Any]] = None):
        try:
            health = {
                'status': status,
                'pid': os.getpid(),
                'uptime_sec': int(time.time() - self.start_time),
                'symbols': {s: self.checkpoint['symbols'].get(s, {}) for s in self.symbols},
                'metrics': dict(self.metrics),
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
            logger.debug("Failed to write crypto health file: %s", e)

    def backfill_historical_bars(self):
        """Backfills historical 1m bars from REST API if checkpoint is behind or empty."""
        logger.info("Checking historical backfill for crypto symbols: %s", self.symbols)
        now_utc = datetime.now(timezone.utc)

        for sym in self.symbols:
            sym_state = self.checkpoint['symbols'].setdefault(sym, {
                'last_bar_timestamp_ms': 0,
                'last_bar_time_iso': None,
                'last_close': None,
                'total_bars_emitted': 0,
            })
            last_ts_ms = sym_state.get('last_bar_timestamp_ms', 0)

            if last_ts_ms > 0:
                start_dt = datetime.fromtimestamp(last_ts_ms / 1000.0, tz=timezone.utc) + timedelta(minutes=1)
            else:
                start_dt = now_utc - timedelta(hours=self.bootstrap_historical_hours)

            # If start_dt is very close to now (less than 2 minutes), no backfill needed
            if (now_utc - start_dt).total_seconds() < 120:
                logger.info("[%s] Bars are up to date (last: %s). Skipping REST backfill.", sym, sym_state.get('last_bar_time_iso'))
                continue

            logger.info("[%s] Backfilling missing bars from %s to %s...", sym, start_dt.strftime('%Y-%m-%d %H:%M:%S UTC'), now_utc.strftime('%Y-%m-%d %H:%M:%S UTC'))

            try:
                req = CryptoBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=TimeFrame.Minute,
                    start=start_dt,
                    end=now_utc - timedelta(minutes=1)
                )
                bars_set = self.hist_client.get_crypto_bars(req)
                bars_list = bars_set.data.get(sym, []) if hasattr(bars_set, 'data') else []

                emitted = 0
                for bar in bars_list:
                    ts = bar.timestamp
                    ts_ms = int(ts.timestamp() * 1000)
                    if ts_ms <= last_ts_ms:
                        continue

                    record = {
                        'asset_type': 'crypto',
                        'symbol': sym,
                        'source': 'alpaca_crypto_rest_backfill',
                        'open': float(bar.open),
                        'high': float(bar.high),
                        'low': float(bar.low),
                        'close': float(bar.close),
                        'volume': float(bar.volume),
                        'trade_count': float(bar.trade_count or 0),
                        'vwap': float(bar.vwap or bar.close),
                        'timestamp': ts_ms,
                        'timestamp_ms': ts_ms,
                        'event_time': int(ts.timestamp()),
                        'ingest_time': int(time.time()),
                        'is_final': True,
                        'schema_version': '1.0'
                    }

                    self.producer.send(
                        topic='crypto-bars-1m',
                        key=sym,
                        value=record,
                        timestamp_ms=ts_ms
                    )
                    last_ts_ms = ts_ms
                    sym_state['last_bar_timestamp_ms'] = ts_ms
                    sym_state['last_bar_time_iso'] = ts.isoformat()
                    sym_state['last_close'] = float(bar.close)
                    sym_state['total_bars_emitted'] = sym_state.get('total_bars_emitted', 0) + 1
                    emitted += 1

                if emitted > 0:
                    self.producer.flush(timeout=10)
                    self._save_checkpoint()
                    self.metrics['bars_emitted'] += emitted
                    self.metrics['last_bar_time'][sym] = sym_state['last_bar_time_iso']
                    logger.info("[%s] Backfilled and published %d historical bars (latest close: $%.2f).", sym, emitted, sym_state['last_close'])
                else:
                    logger.info("[%s] 0 new bars returned from REST API backfill.", sym)

            except Exception as exc:
                logger.warning("[%s] Failed during historical backfill: %s. Continuing to WebSocket stream.", sym, exc)

    def publish_trade(self, raw_trade: dict):
        """Processes and publishes trade message from WebSocket."""
        sym = raw_trade.get('S')
        if not sym:
            return

        t_str = raw_trade.get('t', '')
        try:
            dt = datetime.fromisoformat(t_str.replace('Z', '+00:00'))
            ts_ms = int(dt.timestamp() * 1000)
            event_sec = int(dt.timestamp())
        except Exception:
            ts_ms = int(time.time() * 1000)
            event_sec = int(time.time())

        price = float(raw_trade.get('p', 0.0))
        size = float(raw_trade.get('s', 0.0))

        record = {
            'asset_type': 'crypto',
            'symbol': sym,
            'source': 'alpaca_crypto_ws',
            'price': price,
            'size': size,
            'trade_id': str(raw_trade.get('i', '')),
            'taker_side': str(raw_trade.get('tks', '')),
            'timestamp': ts_ms,
            'timestamp_ms': ts_ms,
            'event_time': event_sec,
            'ingest_time': int(time.time()),
            'schema_version': '1.0'
        }

        try:
            self.producer.send(
                topic='crypto-trades',
                key=sym,
                value=record,
                timestamp_ms=ts_ms
            )
            self.metrics['trades_emitted'] += 1
            self.metrics['last_trade_time'][sym] = datetime.fromtimestamp(event_sec, tz=timezone.utc).isoformat()
        except Exception as e:
            logger.error("[%s] Failed to send crypto trade to Kafka: %s", sym, e)

    def publish_bar(self, raw_bar: dict, is_final: bool = True):
        """Processes and publishes minute bar message from WebSocket."""
        sym = raw_bar.get('S')
        if not sym:
            return

        t_str = raw_bar.get('t', '')
        try:
            dt = datetime.fromisoformat(t_str.replace('Z', '+00:00'))
            ts_ms = int(dt.timestamp() * 1000)
            event_sec = int(dt.timestamp())
        except Exception:
            ts_ms = int(time.time() * 1000)
            event_sec = int(time.time())

        sym_state = self.checkpoint['symbols'].setdefault(sym, {
            'last_bar_timestamp_ms': 0,
            'last_bar_time_iso': None,
            'last_close': None,
            'total_bars_emitted': 0,
        })

        # Deduplication for finalized bars
        if is_final and ts_ms <= sym_state.get('last_bar_timestamp_ms', 0):
            return

        close_price = float(raw_bar.get('c', 0.0))
        record = {
            'asset_type': 'crypto',
            'symbol': sym,
            'source': 'alpaca_crypto_ws',
            'open': float(raw_bar.get('o', 0.0)),
            'high': float(raw_bar.get('h', 0.0)),
            'low': float(raw_bar.get('l', 0.0)),
            'close': close_price,
            'volume': float(raw_bar.get('v', 0.0)),
            'trade_count': float(raw_bar.get('n', 0)),
            'vwap': float(raw_bar.get('vw', close_price)),
            'timestamp': ts_ms,
            'timestamp_ms': ts_ms,
            'event_time': event_sec,
            'ingest_time': int(time.time()),
            'is_final': is_final,
            'schema_version': '1.0'
        }

        try:
            self.producer.send(
                topic='crypto-bars-1m',
                key=sym,
                value=record,
                timestamp_ms=ts_ms
            )
            if is_final:
                sym_state['last_bar_timestamp_ms'] = ts_ms
                sym_state['last_bar_time_iso'] = datetime.fromtimestamp(event_sec, tz=timezone.utc).isoformat()
                sym_state['last_close'] = close_price
                sym_state['total_bars_emitted'] = sym_state.get('total_bars_emitted', 0) + 1
                self._save_checkpoint()
                self.metrics['bars_emitted'] += 1
                self.metrics['last_bar_time'][sym] = sym_state['last_bar_time_iso']
                logger.info("[%s] Published FINAL minute bar @ $%.2f (ts: %s).", sym, close_price, sym_state['last_bar_time_iso'])
            else:
                self.metrics['updated_bars_emitted'] += 1
        except Exception as e:
            logger.error("[%s] Failed to send crypto bar to Kafka: %s", sym, e)

    def fetch_and_publish_crypto_news(self):
        """Polls financial news tagged for crypto symbols, calculates VADER, and publishes."""
        url = "https://data.alpaca.markets/v1beta1/news"
        headers = {
            'APCA-API-KEY-ID': self.key_id,
            'APCA-API-SECRET-KEY': self.secret_key
        }

        # Alpaca news endpoint accepts e.g. BTCUSD, ETHUSD
        crypto_search_map = {
            'BTC/USD': ('BTCUSD', ['bitcoin', 'btc', 'crypto']),
            'ETH/USD': ('ETHUSD', ['ethereum', 'ether', 'eth', 'crypto'])
        }

        for sym, (tag, keywords) in crypto_search_map.items():
            params = {'symbols': tag, 'limit': 10, 'sort': 'desc'}
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code != 200:
                    continue
                news_items = resp.json().get('news', [])
            except Exception as e:
                logger.warning("[%s] Error fetching crypto news: %s", sym, e)
                continue

            new_count = 0
            for item in news_items:
                nid = item.get('id')
                if not nid or nid in self.seen_news_ids:
                    continue

                headline = (item.get('headline') or '').strip()
                summary = (item.get('summary') or '').strip()
                text = f"{headline} {summary}"

                # Compute VADER sentiment
                sentiment_score = float(self.sia.polarity_scores(text).get('compound', 0.0))

                t_str = item.get('created_at', '')
                try:
                    dt = datetime.fromisoformat(t_str.replace('Z', '+00:00'))
                    ts_ms = int(dt.timestamp() * 1000)
                    event_sec = int(dt.timestamp())
                except Exception:
                    ts_ms = int(time.time() * 1000)
                    event_sec = int(time.time())

                article = {
                    'asset_type': 'crypto',
                    'symbol': sym,
                    'source': 'alpaca_crypto_news',
                    'id': nid,
                    'headline': headline,
                    'summary': summary,
                    'author': item.get('author', ''),
                    'url': item.get('url', ''),
                    'sentiment': sentiment_score,
                    'timestamp': ts_ms,
                    'timestamp_ms': ts_ms,
                    'event_time': event_sec,
                    'ingest_time': int(time.time()),
                    'schema_version': '1.0'
                }

                try:
                    self.producer.send(
                        topic='crypto-news',
                        key=sym,
                        value=article,
                        timestamp_ms=ts_ms
                    )
                    self.seen_news_ids.add(nid)
                    new_count += 1
                except Exception as e:
                    logger.error("[%s] Failed to publish crypto news: %s", sym, e)

            if new_count > 0:
                self.producer.flush(timeout=5)
                self._save_news_checkpoint()
                self.metrics['news_emitted'] += new_count
                logger.info("[%s] Published %d new crypto news articles to 'crypto-news'.", sym, new_count)

    def _news_poller_thread(self):
        """Background thread polling crypto news every 90 seconds."""
        logger.info("Crypto news poller thread started.")
        while self.running:
            try:
                self.fetch_and_publish_crypto_news()
            except Exception as e:
                logger.warning("Error in crypto news poller: %s", e)

            # Sleep in small increments for responsive shutdown
            for _ in range(90):
                if not self.running:
                    break
                time.sleep(1)

    async def _websocket_client_loop(self):
        """Async loop managing continuous WebSocket connection, heartbeats, and subscriptions."""
        fail_count = 0
        while self.running:
            try:
                logger.info("Connecting to Alpaca Crypto WebSocket: %s", self.WS_URL)
                async with websockets.connect(self.WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    # 1. Receive connected greeting
                    conn_msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    logger.info("WebSocket connected: %s", conn_msg)

                    # 2. Authenticate
                    auth_payload = {
                        'action': 'auth',
                        'key': self.key_id,
                        'secret': self.secret_key
                    }
                    await ws.send(json.dumps(auth_payload))
                    auth_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                    logger.info("WebSocket auth response: %s", auth_resp)

                    # 3. Subscribe
                    sub_payload = {
                        'action': 'subscribe',
                        'trades': self.symbols,
                        'bars': self.symbols,
                        'updatedBars': self.symbols
                    }
                    await ws.send(json.dumps(sub_payload))
                    sub_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                    logger.info("WebSocket subscription response: %s", sub_resp)

                    fail_count = 0
                    self.backoff_sec = 0
                    self._update_health("RUNNING")

                    # 4. Stream consumer loop
                    while self.running:
                        try:
                            msg_raw = await asyncio.wait_for(ws.recv(), timeout=15)
                            messages = json.loads(msg_raw)
                            for msg in messages:
                                msg_type = msg.get('T')
                                if msg_type == 't':
                                    self.publish_trade(msg)
                                elif msg_type == 'b':
                                    self.publish_bar(msg, is_final=True)
                                elif msg_type == 'u':
                                    self.publish_bar(msg, is_final=False)

                            self._update_health("RUNNING")
                        except asyncio.TimeoutError:
                            # Periodic heartbeat check
                            self._update_health("RUNNING")
                            continue

            except Exception as e:
                if not self.running:
                    break
                fail_count += 1
                self.error_count += 1
                self.backoff_sec = min(60, 2 ** min(fail_count, 6))
                self._update_health("BACKING_OFF", details={'last_error': str(e)})
                logger.warning("Crypto WebSocket error: %s. Backing off for %ds (attempt #%d)...", e, self.backoff_sec, fail_count)
                await asyncio.sleep(self.backoff_sec)

    def start(self):
        self.running = True
        logger.info("=" * 60)
        logger.info("Starting Continuous 24/7 Crypto Market Data & News Streaming")
        logger.info("Symbols: %s", self.symbols)
        logger.info("Brokers: %s", self.brokers)
        logger.info("=" * 60)

        # 1. Backfill historical bars from REST API
        self.backfill_historical_bars()

        # 2. Launch background news poller thread
        news_thread = threading.Thread(target=self._news_poller_thread, daemon=True, name="CryptoNewsPoller")
        news_thread.start()

        # 3. Run Async WebSocket streaming loop
        try:
            asyncio.run(self._websocket_client_loop())
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        logger.info("Stopping Continuous Crypto Producer...")
        self.running = False
        try:
            self.producer.flush(timeout=5)
            self.producer.close(timeout=5)
        except Exception:
            pass
        self._save_checkpoint()
        self._save_news_checkpoint()
        self._update_health("STOPPED")
        logger.info("Continuous Crypto Producer stopped cleanly.")


def main():
    lock = SingleInstanceLock(PID_FILE)
    lock.acquire()

    producer = ContinuousCryptoProducer(symbols=['BTC/USD', 'ETH/USD'])

    def handle_signal(sig, frame):
        logger.info("Received termination signal (%d).", sig)
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

