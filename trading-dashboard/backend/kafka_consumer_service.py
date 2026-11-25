"""
kafka_consumer_service.py — Background Kafka Ingestion & Real-Time Broadcast Service
Reads from Redpanda topics (stock-prices, market-news, trading-signals,
crypto-bars-1m, crypto-trades, crypto-news, crypto-signals),
maintains an in-memory chronological cache, and broadcasts events to WebSocket clients.
"""
import os
import sys
import json
import time
import asyncio
import logging
import threading
from typing import Dict, Any, List, Set, Optional
from datetime import datetime, timezone

try:
    from kafka import KafkaConsumer
except ImportError:
    KafkaConsumer = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('kafka-consumer-service')

# Add libs path if needed
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
libs_dir = os.path.join(base_dir, 'libs')
if libs_dir not in sys.path:
    sys.path.insert(0, libs_dir)

try:
    from alpaca_config.keys import config
except ImportError:
    config = {}

DEFAULT_BROKERS = config.get('redpanda_brokers', os.environ.get('REDPANDA_BROKERS', 'localhost:9092,localhost:9093').split(','))
if isinstance(DEFAULT_BROKERS, str):
    DEFAULT_BROKERS = [b.strip() for b in DEFAULT_BROKERS.split(',')]


def normalize_crypto_symbol(sym: str) -> str:
    s = sym.upper().replace('-', '/')
    if s in ('BTCUSD', 'BTC/USD'):
        return 'BTC/USD'
    if s in ('ETHUSD', 'ETH/USD'):
        return 'ETH/USD'
    return s


class KafkaDataService:
    def __init__(self, brokers: Optional[List[str]] = None):
        self.brokers = brokers or DEFAULT_BROKERS
        self.running = False
        self.consumer_thread: Optional[threading.Thread] = None

        # Data stores: symbol -> {time_sec: candle_dict}
        self.candles: Dict[str, Dict[int, Dict[str, Any]]] = {'NVDA': {}, 'AAPL': {}}
        self.crypto_candles: Dict[str, Dict[int, Dict[str, Any]]] = {'BTC/USD': {}, 'ETH/USD': {}}
        self.crypto_trades: Dict[str, List[Dict[str, Any]]] = {'BTC/USD': [], 'ETH/USD': []}

        # News list (limit 300)
        self.news: List[Dict[str, Any]] = []
        self._seen_news_ids: Set[Any] = set()

        self.crypto_news: List[Dict[str, Any]] = []
        self._seen_crypto_news_ids: Set[Any] = set()

        # Signals list (limit 300)
        self.signals: List[Dict[str, Any]] = []
        self._seen_signals: Set[str] = set()

        self.crypto_signals: List[Dict[str, Any]] = []
        self._seen_crypto_signals: Set[str] = set()

        # Telemetry
        self.is_connected = False
        self.counts = {
            'stock-prices': 0,
            'market-news': 0,
            'trading-signals': 0,
            'crypto-bars-1m': 0,
            'crypto-trades': 0,
            'crypto-news': 0,
            'crypto-signals': 0,
        }
        self.last_event_ts = {
            'stock-prices': None,
            'market-news': None,
            'trading-signals': None,
            'crypto-bars-1m': None,
            'crypto-trades': None,
            'crypto-news': None,
            'crypto-signals': None,
        }
        self.last_ingestion_ts = {
            'stock-prices': None,
            'market-news': None,
            'trading-signals': None,
            'crypto-bars-1m': None,
            'crypto-trades': None,
            'crypto-news': None,
            'crypto-signals': None,
        }

        # WebSocket queues: set of asyncio.Queue
        self.ws_queues: Set[asyncio.Queue] = set()
        self.lock = threading.Lock()

    def register_ws(self, q: asyncio.Queue):
        with self.lock:
            self.ws_queues.add(q)
            logger.info("WebSocket client registered. Total active: %d", len(self.ws_queues))

    def unregister_ws(self, q: asyncio.Queue):
        with self.lock:
            self.ws_queues.discard(q)
            logger.info("WebSocket client unregistered. Total active: %d", len(self.ws_queues))

    def _broadcast(self, event_type: str, data: Any):
        """Thread-safe dispatch to all connected WebSocket queues."""
        msg = {'type': event_type, 'data': data}
        with self.lock:
            for q in list(self.ws_queues):
                try:
                    q.put_nowait(msg)
                except Exception:
                    pass

    def get_candles(self, symbol: str) -> List[Dict[str, Any]]:
        """Return sorted 1m candles for stock or crypto symbol."""
        sym_norm = symbol.upper().replace('-', '/')
        with self.lock:
            if sym_norm in ('BTC/USD', 'ETH/USD', 'BTCUSD', 'ETHUSD'):
                key = 'BTC/USD' if 'BTC' in sym_norm else 'ETH/USD'
                c_dict = self.crypto_candles.get(key, {})
            else:
                c_dict = self.candles.get(sym_norm, {})
            return [c_dict[t] for t in sorted(c_dict.keys())]

    def get_crypto_candles(self, symbol: str) -> List[Dict[str, Any]]:
        """Return sorted 1m crypto candles."""
        key = normalize_crypto_symbol(symbol)
        with self.lock:
            c_dict = self.crypto_candles.get(key, {})
            return [c_dict[t] for t in sorted(c_dict.keys())]

    def get_crypto_trades(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        key = normalize_crypto_symbol(symbol)
        with self.lock:
            trades = list(self.crypto_trades.get(key, []))
            return trades[:limit]

    def get_news(self, symbol: Optional[str] = None, sentiment_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.news)
            if not symbol or symbol.upper() in ('BTC/USD', 'ETH/USD', 'BTCUSD', 'ETHUSD'):
                items = list(self.crypto_news) + items
        if symbol:
            sym_clean = normalize_crypto_symbol(symbol)
            items = [n for n in items if n.get('symbol') in (symbol.upper(), sym_clean)]
        if sentiment_filter:
            sf = sentiment_filter.upper()
            if sf == 'POSITIVE' or sf == 'BULLISH':
                items = [n for n in items if float(n.get('sentiment', 0.0)) > 0.05]
            elif sf == 'NEGATIVE' or sf == 'BEARISH':
                items = [n for n in items if float(n.get('sentiment', 0.0)) < -0.05]
            elif sf == 'NEUTRAL':
                items = [n for n in items if -0.05 <= float(n.get('sentiment', 0.0)) <= 0.05]
        return items

    def get_crypto_news(self, symbol: Optional[str] = None, sentiment_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.crypto_news)
        if symbol:
            sym_clean = normalize_crypto_symbol(symbol)
            items = [n for n in items if n.get('symbol') == sym_clean]
        if sentiment_filter:
            sf = sentiment_filter.upper()
            if sf in ('POSITIVE', 'BULLISH'):
                items = [n for n in items if float(n.get('sentiment', 0.0)) > 0.05]
            elif sf in ('NEGATIVE', 'BEARISH'):
                items = [n for n in items if float(n.get('sentiment', 0.0)) < -0.05]
            elif sf == 'NEUTRAL':
                items = [n for n in items if -0.05 <= float(n.get('sentiment', 0.0)) <= 0.05]
        return items

    def get_signals(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.signals)
            if not symbol or symbol.upper() in ('BTC/USD', 'ETH/USD', 'BTCUSD', 'ETHUSD'):
                items = list(self.crypto_signals) + items
        if symbol:
            sym_clean = normalize_crypto_symbol(symbol)
            items = [s for s in items if s.get('symbol') in (symbol.upper(), sym_clean)]
        return items

    def get_crypto_signals(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.crypto_signals)
        if symbol:
            sym_clean = normalize_crypto_symbol(symbol)
            items = [s for s in items if s.get('symbol') == sym_clean]
        return items

    def get_last_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym_norm = normalize_crypto_symbol(symbol)
        with self.lock:
            if sym_norm in ('BTC/USD', 'ETH/USD'):
                c_dict = self.crypto_candles.get(sym_norm, {})
            else:
                c_dict = self.candles.get(symbol.upper(), {})
            if not c_dict:
                return None
            last_t = max(c_dict.keys())
            return c_dict[last_t]

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'redpanda_connected': self.is_connected,
                'brokers': self.brokers,
                'topic_counts': dict(self.counts),
                'last_event_timestamps': dict(self.last_event_ts),
                'last_ingestion_timestamps': dict(self.last_ingestion_ts),
                'active_ws_clients': len(self.ws_queues),
                'total_candles_nvda': len(self.candles.get('NVDA', {})),
                'total_candles_aapl': len(self.candles.get('AAPL', {})),
                'total_candles_btc': len(self.crypto_candles.get('BTC/USD', {})),
                'total_candles_eth': len(self.crypto_candles.get('ETH/USD', {})),
                'total_news': len(self.news),
                'total_crypto_news': len(self.crypto_news),
                'total_signals': len(self.signals),
                'total_crypto_signals': len(self.crypto_signals),
            }

    def _process_price_message(self, val: dict):
        sym = val.get('symbol', '').upper()
        if not sym:
            return

        raw_ts = val.get('timestamp')
        if not raw_ts:
            return
        ts_sec = int(raw_ts // 1000) if raw_ts > 100000000000 else int(raw_ts)

        now_sec = int(time.time())
        candle = {
            'asset_type': 'STOCKS',
            'symbol': sym,
            'time': ts_sec,
            'event_time': val.get('event_time', ts_sec),
            'ingest_time': val.get('ingest_time', now_sec),
            'processed_at': now_sec,
            'open': float(val.get('open', 0.0)),
            'high': float(val.get('high', 0.0)),
            'low': float(val.get('low', 0.0)),
            'close': float(val.get('close', 0.0)),
            'volume': float(val.get('volume', 0.0)),
            'trade_count': float(val.get('trade_count', 0.0)),
            'vwap': float(val.get('vwap', val.get('close', 0.0))),
            'provider': val.get('provider', 'alpaca'),
        }

        with self.lock:
            if sym not in self.candles:
                self.candles[sym] = {}
            self.candles[sym][ts_sec] = candle
            self.counts['stock-prices'] += 1
            self.last_event_ts['stock-prices'] = ts_sec
            self.last_ingestion_ts['stock-prices'] = now_sec

        self._broadcast('candle', candle)

    def _process_crypto_bar_message(self, val: dict):
        raw_sym = val.get('symbol', '')
        sym = normalize_crypto_symbol(raw_sym)
        if not sym:
            return

        raw_ts = val.get('timestamp_ms') or val.get('timestamp')
        if not raw_ts:
            return
        ts_sec = int(raw_ts // 1000) if raw_ts > 100000000000 else int(raw_ts)
        now_sec = int(time.time())

        candle = {
            'asset_type': 'CRYPTO',
            'symbol': sym,
            'time': ts_sec,
            'event_time': val.get('event_time', ts_sec),
            'ingest_time': val.get('ingest_time', now_sec),
            'processed_at': now_sec,
            'open': float(val.get('open', 0.0)),
            'high': float(val.get('high', 0.0)),
            'low': float(val.get('low', 0.0)),
            'close': float(val.get('close', 0.0)),
            'volume': float(val.get('volume', 0.0)),
            'trade_count': float(val.get('trade_count', 0.0)),
            'vwap': float(val.get('vwap', val.get('close', 0.0))),
            'provider': val.get('provider', 'alpaca_crypto_ws'),
            'is_final': bool(val.get('is_final', True)),
        }

        with self.lock:
            if sym not in self.crypto_candles:
                self.crypto_candles[sym] = {}
            self.crypto_candles[sym][ts_sec] = candle
            self.counts['crypto-bars-1m'] += 1
            self.last_event_ts['crypto-bars-1m'] = ts_sec
            self.last_ingestion_ts['crypto-bars-1m'] = now_sec

        # Broadcast both crypto_candle and generic candle for frontend compatibility
        self._broadcast('crypto_candle', candle)
        self._broadcast('candle', candle)

    def _process_crypto_trade_message(self, val: dict):
        raw_sym = val.get('symbol', '')
        sym = normalize_crypto_symbol(raw_sym)
        if not sym:
            return

        raw_ts = val.get('timestamp_ms') or int(time.time() * 1000)
        ts_sec = int(raw_ts // 1000) if raw_ts > 100000000000 else int(raw_ts)
        price = float(val.get('price', 0.0))
        size = float(val.get('size', 0.0))

        trade_item = {
            'asset_type': 'CRYPTO',
            'symbol': sym,
            'trade_id': val.get('trade_id'),
            'price': price,
            'size': size,
            'time': ts_sec,
            'takerside': val.get('takerside', ''),
        }

        with self.lock:
            if sym not in self.crypto_trades:
                self.crypto_trades[sym] = []
            self.crypto_trades[sym].insert(0, trade_item)
            if len(self.crypto_trades[sym]) > 100:
                self.crypto_trades[sym].pop()

            self.counts['crypto-trades'] += 1
            self.last_event_ts['crypto-trades'] = ts_sec
            self.last_ingestion_ts['crypto-trades'] = int(time.time())

            # Update latest candle close in memory if existing
            c_dict = self.crypto_candles.get(sym, {})
            if c_dict:
                last_t = max(c_dict.keys())
                # Update current active minute candle
                if abs(ts_sec - last_t) < 60:
                    c = c_dict[last_t]
                    c['close'] = price
                    c['high'] = max(c['high'], price)
                    c['low'] = min(c['low'], price)
                    c['volume'] += size

        self._broadcast('crypto_trade', trade_item)

    def _process_news_message(self, val: dict):
        news_id = val.get('id') or val.get('headline')
        if not news_id or news_id in self._seen_news_ids:
            return
        self._seen_news_ids.add(news_id)

        raw_ts = val.get('timestamp_ms') or int(time.time() * 1000)
        ts_sec = int(raw_ts // 1000) if raw_ts > 100000000000 else int(raw_ts)

        sentiment_score = float(val.get('sentiment', 0.0))
        if sentiment_score > 0.05:
            sentiment_label = 'POSITIVE'
        elif sentiment_score < -0.05:
            sentiment_label = 'NEGATIVE'
        else:
            sentiment_label = 'NEUTRAL'

        news_item = {
            'id': val.get('id'),
            'asset_type': 'STOCKS',
            'symbol': val.get('symbol', 'ALL').upper(),
            'headline': val.get('headline', ''),
            'summary': val.get('summary', ''),
            'author': val.get('author', ''),
            'source': val.get('source', ''),
            'url': val.get('url', ''),
            'sentiment': sentiment_score,
            'sentiment_label': sentiment_label,
            'time': ts_sec,
            'timestamp_iso': datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        }

        with self.lock:
            self.news.insert(0, news_item)
            if len(self.news) > 300:
                self.news.pop()
            self.counts['market-news'] += 1
            self.last_event_ts['market-news'] = ts_sec
            self.last_ingestion_ts['market-news'] = int(time.time())

        self._broadcast('news', news_item)

    def _process_crypto_news_message(self, val: dict):
        news_id = val.get('id') or val.get('headline')
        if not news_id or news_id in self._seen_crypto_news_ids:
            return
        self._seen_crypto_news_ids.add(news_id)

        raw_ts = val.get('timestamp_ms') or int(time.time() * 1000)
        ts_sec = int(raw_ts // 1000) if raw_ts > 100000000000 else int(raw_ts)

        sentiment_score = float(val.get('sentiment', 0.0))
        if sentiment_score > 0.05:
            sentiment_label = 'POSITIVE'
        elif sentiment_score < -0.05:
            sentiment_label = 'NEGATIVE'
        else:
            sentiment_label = 'NEUTRAL'

        raw_sym = val.get('symbol', 'CRYPTO')
        sym = normalize_crypto_symbol(raw_sym)

        news_item = {
            'id': val.get('id'),
            'asset_type': 'CRYPTO',
            'symbol': sym,
            'headline': val.get('headline', ''),
            'summary': val.get('summary', ''),
            'author': val.get('author', ''),
            'source': val.get('source', 'Alpaca Crypto News'),
            'url': val.get('url', ''),
            'sentiment': sentiment_score,
            'sentiment_label': sentiment_label,
            'time': ts_sec,
            'timestamp_iso': datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        }

        with self.lock:
            self.crypto_news.insert(0, news_item)
            if len(self.crypto_news) > 300:
                self.crypto_news.pop()
            self.counts['crypto-news'] += 1
            self.last_event_ts['crypto-news'] = ts_sec
            self.last_ingestion_ts['crypto-news'] = int(time.time())

        self._broadcast('crypto_news', news_item)
        self._broadcast('news', news_item)

    def _process_signal_message(self, val: dict):
        sym = val.get('symbol', '').upper()
        sig = str(val.get('signal', '')).upper()
        sig_time = val.get('signal_time', '')
        dedup_key = f"{sym}:{sig}:{sig_time}"

        if dedup_key in self._seen_signals:
            return
        self._seen_signals.add(dedup_key)

        ts_sec = int(time.time())
        try:
            if sig_time:
                cleaned = sig_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(cleaned)
                ts_sec = int(dt.timestamp())
        except Exception:
            pass

        price_near_signal = None
        with self.lock:
            sym_candles = self.candles.get(sym, {})
            if sym_candles:
                closest_time = min(sym_candles.keys(), key=lambda t: abs(t - ts_sec))
                price_near_signal = sym_candles[closest_time].get('close')

        signal_item = {
            'asset_type': 'STOCKS',
            'symbol': sym,
            'signal': sig,
            'time': ts_sec,
            'signal_time_str': sig_time,
            'price_at_signal': price_near_signal,
        }

        with self.lock:
            self.signals.insert(0, signal_item)
            if len(self.signals) > 300:
                self.signals.pop()
            self.counts['trading-signals'] += 1
            self.last_event_ts['trading-signals'] = ts_sec
            self.last_ingestion_ts['trading-signals'] = int(time.time())

        self._broadcast('signal', signal_item)

    def _process_crypto_signal_message(self, val: dict):
        raw_sym = val.get('symbol', '')
        sym = normalize_crypto_symbol(raw_sym)
        sig = str(val.get('signal', '')).upper()
        sig_time = val.get('signal_time', '')
        dedup_key = f"{sym}:{sig}:{sig_time}"

        if dedup_key in self._seen_crypto_signals:
            return
        self._seen_crypto_signals.add(dedup_key)

        ts_sec = int(time.time())
        try:
            if sig_time:
                cleaned = sig_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(cleaned)
                ts_sec = int(dt.timestamp())
        except Exception:
            pass

        price_near_signal = None
        with self.lock:
            sym_candles = self.crypto_candles.get(sym, {})
            if sym_candles:
                closest_time = min(sym_candles.keys(), key=lambda t: abs(t - ts_sec))
                price_near_signal = sym_candles[closest_time].get('close')

        signal_item = {
            'asset_type': 'CRYPTO',
            'symbol': sym,
            'signal': sig,
            'time': ts_sec,
            'signal_time_str': sig_time,
            'price_at_signal': price_near_signal,
            'sentiment': val.get('sentiment'),
            'sma_20': val.get('sma_20'),
            'sma_50': val.get('sma_50'),
        }

        with self.lock:
            self.crypto_signals.insert(0, signal_item)
            if len(self.crypto_signals) > 300:
                self.crypto_signals.pop()
            self.counts['crypto-signals'] += 1
            self.last_event_ts['crypto-signals'] = ts_sec
            self.last_ingestion_ts['crypto-signals'] = int(time.time())

        self._broadcast('crypto_signal', signal_item)
        self._broadcast('signal', signal_item)

    def _run_consumer(self):
        logger.info("Kafka consumer thread starting. Connecting to brokers: %s", self.brokers)
        subscribed_topics = [
            'stock-prices', 'market-news', 'trading-signals',
            'crypto-bars-1m', 'crypto-trades', 'crypto-news', 'crypto-signals'
        ]
        while self.running:
            try:
                consumer = KafkaConsumer(
                    *subscribed_topics,
                    bootstrap_servers=self.brokers,
                    auto_offset_reset='earliest',
                    enable_auto_commit=False,
                    group_id=f"dashboard-session-{os.getpid()}-{int(time.time())}",
                    value_deserializer=lambda v: json.loads(v.decode('utf-8', errors='ignore')),
                    consumer_timeout_ms=1000,
                )
                self.is_connected = True
                logger.info("Kafka consumer connected successfully to all topics: %s", subscribed_topics)

                while self.running:
                    for record in consumer:
                        if not self.running:
                            break
                        try:
                            topic = record.topic
                            val = record.value
                            if topic == 'stock-prices':
                                self._process_price_message(val)
                            elif topic == 'market-news':
                                self._process_news_message(val)
                            elif topic == 'trading-signals':
                                self._process_signal_message(val)
                            elif topic == 'crypto-bars-1m':
                                self._process_crypto_bar_message(val)
                            elif topic == 'crypto-trades':
                                self._process_crypto_trade_message(val)
                            elif topic == 'crypto-news':
                                self._process_crypto_news_message(val)
                            elif topic == 'crypto-signals':
                                self._process_crypto_signal_message(val)
                        except Exception as e:
                            logger.error("Error processing record on topic %s: %s", record.topic, e)

                    time.sleep(0.05)

                consumer.close()
            except Exception as exc:
                self.is_connected = False
                logger.warning("Kafka consumer error: %s. Reconnecting in 3 seconds...", exc)
                time.sleep(3)

    def start(self):
        if self.running:
            return
        if KafkaConsumer is None:
            logger.warning("kafka library not installed; KafkaConsumer background worker disabled.")
            return
        self.running = True
        self.consumer_thread = threading.Thread(target=self._run_consumer, daemon=True, name="KafkaConsumerThread")
        self.consumer_thread.start()

    def stop(self):
        self.running = False
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=2)


# Global singleton instance
kafka_service = KafkaDataService()
