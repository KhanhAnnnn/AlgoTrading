"""
news-producer.py — Alpaca News Producer
Fetches historical and live news from Alpaca REST API, computes
NLTK VADER compound sentiment scores, and publishes to Redpanda topic 'market-news'.
"""
import json
import sys
import os
import logging
from typing import List
from datetime import datetime, date
import requests
from kafka import KafkaProducer
from nltk.sentiment.vader import SentimentIntensityAnalyzer as SIA

# Make sure libs/ is on the path so alpaca_config can be found
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
from alpaca_config.keys import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('news-producer')

sia = SIA()


def get_sentiment(text: str) -> float:
    scores = sia.polarity_scores(text)
    return float(scores['compound'])


def get_producer(brokers: List[str]) -> KafkaProducer:
    producer = KafkaProducer(
        bootstrap_servers=brokers,
        key_serializer=str.encode,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer


def produce_historical_news(
        redpanda_client: KafkaProducer,
        symbols: List[List[str]],
        topic: str = 'market-news',
        limit: int = 50
):
    key_id = config['key_id']
    secret_key = config['secret_key']

    if not key_id or not secret_key:
        logger.error("Alpaca credentials missing. Set ALPACA_KEY_ID and ALPACA_SECRET_KEY in .env.")
        return

    headers = {
        'APCA-API-KEY-ID': key_id,
        'APCA-API-SECRET-KEY': secret_key
    }

    url = "https://data.alpaca.markets/v1beta1/news"

    for symbol in symbols:
        target_symbol = symbol[0]
        keywords = [k.lower() for k in symbol]
        sent_count = 0

        params = {'symbols': target_symbol, 'limit': limit, 'sort': 'desc'}
        logger.info("Fetching news from %s for %s (limit=%d)...", url, target_symbol, limit)
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                logger.error("Alpaca News API error %s: %s", response.status_code, response.text)
                continue
            data = response.json()
            news_items = data.get('news', [])
        except Exception as exc:
            logger.error("Failed to connect to Alpaca News API: %s", exc)
            continue

        logger.info("Retrieved %d news articles from Alpaca for %s", len(news_items), target_symbol)

        for row in news_items:
            headline = row.get('headline') or ''
            summary = (row.get('summary') or '').strip()
            article_symbols = row.get('symbols', [])

            # Match if target symbol is tagged OR if headline/summary mentions keywords
            is_symbol_tagged = target_symbol in article_symbols
            text_to_search = (headline + " " + summary).lower()
            keyword_match = any(kw in text_to_search for kw in keywords)

            if not (is_symbol_tagged or keyword_match):
                continue

            # Parse timestamp
            created_at_str = row.get('created_at', '')
            try:
                dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                timestamp_ms = int(dt.timestamp() * 1000)
                timestamp_fmt = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                timestamp_ms = int(datetime.now().timestamp() * 1000)
                timestamp_fmt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            sentiment_text = headline + (" " + summary if summary else "")
            sentiment_score = get_sentiment(sentiment_text)

            article = {
                'id': row.get('id'),
                'author': row.get('author', ''),
                'headline': headline,
                'source': row.get('source', ''),
                'summary': summary,
                'data_provider': 'alpaca',
                'url': row.get('url', ''),
                'symbol': target_symbol,
                'sentiment': sentiment_score,
                'timestamp_ms': timestamp_ms,
            }

            try:
                future = redpanda_client.send(
                    topic=topic,
                    key=target_symbol,
                    value=article,
                    timestamp_ms=timestamp_ms
                )
                future.get(timeout=10)
                sent_count += 1
                logger.info(
                    "[%s] Sent #%d: sentiment=%.4f | headline=%s",
                    target_symbol, sent_count, sentiment_score, headline[:60]
                )
            except Exception as exc:
                logger.error("Failed to send article to topic %s: %s", topic, exc)

        logger.info("Total articles published for %s: %d", target_symbol, sent_count)


if __name__ == '__main__':
    brokers = config['redpanda_brokers']
    logger.info("Connecting to Redpanda brokers: %s", brokers)
    redpanda_client = get_producer(brokers)

    produce_historical_news(
        redpanda_client=redpanda_client,
        symbols=[['NVDA', 'NVIDIA']],
        topic='market-news',
        limit=50
    )

    redpanda_client.close()
    logger.info("News producer completed.")