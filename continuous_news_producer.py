"""
continuous_news_producer.py — Production-Grade Continuous Alpaca News & Sentiment Producer
Polls financial news from Alpaca News REST API, computes NLTK VADER compound sentiment scores,
enforces deduplication via persistent checkpoints, handles rate limits,
and publishes to Redpanda topic 'market-news'.
"""
import os
import sys
import time
import json
import signal
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional
import psutil
import requests

from kafka import KafkaProducer, KafkaConsumer, TopicPartition
import nltk

# Ensure VADER lexicon is present
try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon', quiet=True)

from nltk.sentiment.vader import SentimentIntensityAnalyzer as SIA

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

PID_FILE = os.path.join(LOCK_DIR, 'news_producer.pid')
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'news_checkpoint.json')
HEALTH_FILE = os.path.join(STATUS_DIR, 'news_producer_health.json')
LOG_FILE = os.path.join(LOGS_DIR, 'news_producer.log')

# Setup Logging with Rotation
logger = logging.getLogger('continuous-news-producer')
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
                    if psutil.pid_exists(old_pid):
                        proc = psutil.Process(old_pid)
                        if 'python' in proc.name().lower() and old_pid != os.getpid():
                            logger.error("Another News Producer instance (PID %d) is already active.", old_pid)
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


class ContinuousNewsProducer:
    def __init__(
        self,
        symbols_map: Optional[Dict[str, List[str]]] = None,
        topic: str = 'market-news',
        poll_interval_sec: int = 90,
    ):
        self.symbols_map = symbols_map or {
            'NVDA': ['NVDA', 'NVIDIA'],
            'AAPL': ['AAPL', 'APPLE'],
        }
        self.topic = topic
        self.poll_interval_sec = poll_interval_sec
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

        self.news_base_url = config.get('news_base_url', 'https://data.alpaca.markets')

        if not self.key_id or not self.secret_key:
            logger.error("Alpaca credentials missing in environment/.env.")
            sys.exit(1)

        self.sia = SIA()

        self.producer = KafkaProducer(
            bootstrap_servers=self.brokers,
            key_serializer=str.encode,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5,
            acks='all'
        )

        self.checkpoint = self._load_checkpoint()
        self.seen_ids: Set[Any] = set(self.checkpoint.get('seen_article_ids', []))

        # If seen_ids is empty, bootstrap from existing Kafka records
        if not self.seen_ids:
            self._bootstrap_seen_ids_from_kafka_if_needed()

    def _bootstrap_seen_ids_from_kafka_if_needed(self):
        """Scans Kafka market-news topic to pre-populate seen_ids if news_checkpoint is empty."""
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
                    consumer.seek(tp, max(0, end - 1000))
                    for msg in consumer:
                        try:
                            val = json.loads(msg.value.decode('utf-8'))
                            nid = val.get('id')
                            if nid:
                                self.seen_ids.add(nid)
                        except Exception:
                            continue
            consumer.close()
            logger.info("Bootstrapped %d seen news IDs from Kafka topic '%s'.", len(self.seen_ids), self.topic)
            self._save_checkpoint()
        except Exception as e:
            logger.warning("Could not bootstrap seen news IDs from Kafka: %s", e)

    def _load_checkpoint(self) -> Dict[str, Any]:
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Loaded news checkpoint (%d seen IDs).", len(data.get('seen_article_ids', [])))
                    return data
            except Exception as e:
                logger.warning("Failed to load news checkpoint: %s. Creating new state.", e)

        return {
            'seen_article_ids': [],
            'last_article_id': None,
            'last_article_timestamp_ms': 0,
            'total_articles_emitted': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    def _save_checkpoint(self):
        try:
            recent_ids = list(self.seen_ids)[-2000:]
            self.checkpoint['seen_article_ids'] = recent_ids
            self.checkpoint['last_updated_at'] = datetime.now(timezone.utc).isoformat()
            temp_file = CHECKPOINT_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint, f, indent=2)
            os.replace(temp_file, CHECKPOINT_FILE)
        except Exception as e:
            logger.error("Failed to save news checkpoint: %s", e)

    def _update_health(self, status: str, details: Optional[Dict[str, Any]] = None):
        try:
            health = {
                'status': status,
                'pid': os.getpid(),
                'uptime_sec': int(time.time() - self.start_time),
                'total_seen_ids': len(self.seen_ids),
                'total_emitted': self.checkpoint.get('total_articles_emitted', 0),
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
            logger.debug("Failed to write news health file: %s", e)

    def compute_sentiment(self, text: str) -> float:
        scores = self.sia.polarity_scores(text)
        return float(scores.get('compound', 0.0))

    def fetch_and_publish_news(self, symbol: str, keywords: List[str], limit: int = 20) -> int:
        url = f"{self.news_base_url}/v1beta1/news"
        headers = {
            'APCA-API-KEY-ID': self.key_id,
            'APCA-API-SECRET-KEY': self.secret_key
        }
        params = {
            'symbols': symbol,
            'limit': limit,
            'sort': 'desc'
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 429:
                logger.warning("[%s] Alpaca News API rate-limited (HTTP 429).", symbol)
                raise requests.HTTPError("Rate limited (429)", response=response)
            if response.status_code != 200:
                logger.error("[%s] Alpaca News API error %s: %s", symbol, response.status_code, response.text)
                return 0
            data = response.json()
            news_items = data.get('news', [])
        except Exception as exc:
            self.error_count += 1
            logger.error("[%s] Failed to fetch news from Alpaca: %s", symbol, exc)
            raise exc

        new_count = 0
        keywords_lower = [k.lower() for k in keywords]

        for row in news_items:
            news_id = row.get('id')
            if not news_id or news_id in self.seen_ids:
                continue

            headline = (row.get('headline') or '').strip()
            summary = (row.get('summary') or '').strip()
            article_symbols = row.get('symbols', [])

            is_symbol_tagged = symbol in article_symbols
            text_to_search = (headline + " " + summary).lower()
            keyword_match = any(kw in text_to_search for kw in keywords_lower)

            if not (is_symbol_tagged or keyword_match):
                continue

            # Parse event time
            created_at_str = row.get('created_at', '')
            try:
                dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                timestamp_ms = int(dt.timestamp() * 1000)
            except Exception:
                timestamp_ms = int(time.time() * 1000)

            sentiment_text = f"{headline} {summary}".strip()
            sentiment_score = self.compute_sentiment(sentiment_text)

            article = {
                'id': news_id,
                'author': row.get('author', ''),
                'headline': headline,
                'source': row.get('source', ''),
                'summary': summary,
                'data_provider': 'alpaca',
                'url': row.get('url', ''),
                'symbol': symbol,
                'sentiment': sentiment_score,
                'timestamp_ms': timestamp_ms,
            }

            try:
                self.producer.send(
                    topic=self.topic,
                    key=symbol,
                    value=article,
                    timestamp_ms=timestamp_ms
                )
                self.seen_ids.add(news_id)
                new_count += 1
                self.checkpoint['last_article_id'] = news_id
                self.checkpoint['last_article_timestamp_ms'] = timestamp_ms
                self.checkpoint['total_articles_emitted'] = self.checkpoint.get('total_articles_emitted', 0) + 1
            except Exception as e:
                logger.error("[%s] Failed to publish article %s: %s", symbol, news_id, e)
                raise e

        if new_count > 0:
            self.producer.flush(timeout=10)
            self._save_checkpoint()
            logger.info("[%s] Published %d new articles to '%s'.", symbol, new_count, self.topic)

        return new_count

    def start(self):
        self.running = True
        logger.info("Starting Continuous News Producer for symbols: %s", list(self.symbols_map.keys()))

        fail_count = 0
        while self.running:
            try:
                batch_count = 0
                for sym, kws in self.symbols_map.items():
                    if not self.running:
                        break
                    count = self.fetch_and_publish_news(sym, kws)
                    batch_count += count

                fail_count = 0
                self.backoff_sec = 0
                self._update_health("RUNNING", details={'last_batch_new_articles': batch_count})

                time.sleep(self.poll_interval_sec)

            except Exception as e:
                fail_count += 1
                self.error_count += 1
                self.backoff_sec = min(60, 2 ** min(fail_count, 6))
                self._update_health("BACKING_OFF", details={'last_error': str(e)})
                logger.warning("News producer error: %s. Backing off for %ds (retry #%d)...", e, self.backoff_sec, fail_count)
                time.sleep(self.backoff_sec)

    def stop(self):
        logger.info("Stopping Continuous News Producer...")
        self.running = False
        try:
            self.producer.flush(timeout=5)
            self.producer.close(timeout=5)
        except Exception:
            pass
        self._save_checkpoint()
        self._update_health("STOPPED")
        logger.info("Continuous News Producer cleanly terminated.")


def main():
    lock = SingleInstanceLock(PID_FILE)
    lock.acquire()

    producer = ContinuousNewsProducer(poll_interval_sec=90)

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
