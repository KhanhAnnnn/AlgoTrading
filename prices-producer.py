"""
prices-producer.py — Alpaca Stock Prices Producer
Fetches 1-minute OHLCV historical stock bars from Alpaca,
serializes to JSON, and publishes to Redpanda topic 'stock-prices'.
"""
import json
import logging
import sys
import os
from datetime import datetime, date, timedelta, timezone
from typing import List

from alpaca.data import StockHistoricalDataClient, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from kafka import KafkaProducer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
from alpaca_config.keys import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('prices-producer')


def get_producer(brokers: List[str]) -> KafkaProducer:
    producer = KafkaProducer(
        bootstrap_servers=brokers,
        key_serializer=str.encode,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer


def produce_historical_price(
        redpanda_client: KafkaProducer,
        topic: str = 'stock-prices',
        symbol: str = 'NVDA',
        days_back: int = 5
):
    key_id = config['key_id']
    secret_key = config['secret_key']

    if not key_id or not secret_key:
        logger.error("Alpaca credentials missing. Set ALPACA_KEY_ID and ALPACA_SECRET_KEY in .env.")
        return

    client = StockHistoricalDataClient(api_key=key_id, secret_key=secret_key)

    # 15-min delay buffer for free tier IEX feed
    end_date = datetime.now(timezone.utc) - timedelta(minutes=20)
    start_date = end_date - timedelta(days=days_back)

    logger.info("Fetching 1-min bars for %s from %s to %s (IEX feed)...", symbol, start_date.strftime('%Y-%m-%d %H:%M'), end_date.strftime('%Y-%m-%d %H:%M'))

    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start_date,
        end=end_date,
        feed=DataFeed.IEX
    )

    try:
        bars = client.get_stock_bars(request_params)
        prices_df = bars.df
        if prices_df is None or prices_df.empty:
            logger.warning("No price bars returned for %s in specified range.", symbol)
            return
    except Exception as exc:
        logger.error("Failed to fetch stock bars for %s: %s", symbol, exc)
        return

    prices_df = prices_df.reset_index()
    logger.info("Retrieved %d bars for %s. Preparing to push to Redpanda...", len(prices_df), symbol)

    records = json.loads(prices_df.to_json(orient='records'))
    success_count = 0

    for idx, record in enumerate(records):
        record['provider'] = 'alpaca'
        ts_ms = int(record['timestamp'])

        try:
            future = redpanda_client.send(
                topic=topic,
                key=record['symbol'],
                value=record,
                timestamp_ms=ts_ms
            )
            # Flush in batches
            if (idx + 1) % 200 == 0 or idx == len(records) - 1:
                future.get(timeout=10)
                logger.info("[%s] Emitted %d/%d bars (latest close: $%.2f)", symbol, idx + 1, len(records), record['close'])
            success_count += 1
        except Exception as exc:
            logger.error("Error sending bar #%d: %s", idx, exc)

    logger.info("Completed: published %d bars to topic '%s' for %s", success_count, topic, symbol)


if __name__ == '__main__':
    brokers = config['redpanda_brokers']
    logger.info("Connecting to Redpanda brokers: %s", brokers)
    redpanda_client = get_producer(brokers)

    produce_historical_price(
        redpanda_client=redpanda_client,
        topic='stock-prices',
        symbol='NVDA',
        days_back=5
    )

    redpanda_client.close()
    logger.info("Price producer completed.")
