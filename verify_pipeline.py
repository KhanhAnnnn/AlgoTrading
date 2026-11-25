"""
verify_pipeline.py — Controlled Signal Generation Verification
Emits 25 price bars and 2 news articles so that:
- News 1 (min 19): Close = $100.0, SMA20 = $100.0 (LAG is NULL)
- News 2 (min 20): Close = $95.0, SMA20 = $99.75 (LAG = $100.0 >= SMA20, Close < SMA20, Sentiment > 0)
-> Triggers BUY signal!
"""
import json
import time
from datetime import datetime, timezone, timedelta
from kafka import KafkaProducer, KafkaConsumer

BROKERS = ['localhost:9092', 'localhost:9093']
SYMBOL = 'TEST_NVDA'

producer = KafkaProducer(
    bootstrap_servers=BROKERS,
    key_serializer=str.encode,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

base_time = datetime(2026, 10, 17, 9, 0, 0, tzinfo=timezone.utc)

print(f"1. Emitting 25 price bars for {SYMBOL}...")
# 20 bars at $100.0, followed by bars at $95.0, $94.0...
prices = [100.0] * 20 + [95.0, 94.0, 93.0, 92.0, 91.0]

for i, p in enumerate(prices):
    bar_time = base_time + timedelta(minutes=i)
    bar_ts = int(bar_time.timestamp() * 1000)
    bar = {
        'symbol': SYMBOL,
        'open': p,
        'high': p + 0.5,
        'low': p - 0.5,
        'close': p,
        'volume': 1000.0,
        'trade_count': 50.0,
        'vwap': p,
        'provider': 'alpaca',
        'timestamp': bar_ts
    }
    producer.send('stock-prices', key=SYMBOL, value=bar, timestamp_ms=bar_ts)

# News 1 at minute 19 (within 1 min of bar 19 at $100)
news1_time = base_time + timedelta(minutes=19, seconds=-10)
news1_ts = int(news1_time.timestamp() * 1000)
news1 = {
    'id': 88880001,
    'author': 'Tester',
    'headline': f'{SYMBOL} Baseline News Event',
    'source': 'benzinga',
    'summary': 'Holding steady at moving average.',
    'data_provider': 'alpaca',
    'url': 'https://example.com/test1',
    'symbol': SYMBOL,
    'sentiment': 0.50,
    'timestamp_ms': news1_ts
}
print(f"2. Emitting News 1 (Baseline) at minute 19...")
producer.send('market-news', key=SYMBOL, value=news1, timestamp_ms=news1_ts)

# News 2 at minute 20 (within 1 min of bar 20 at $95)
news2_time = base_time + timedelta(minutes=20, seconds=-10)
news2_ts = int(news2_time.timestamp() * 1000)
news2 = {
    'id': 88880002,
    'author': 'Tester',
    'headline': f'{SYMBOL} Deep Dip Buying Opportunity Announced',
    'source': 'benzinga',
    'summary': 'Bullish momentum poised to recover after sudden dip.',
    'data_provider': 'alpaca',
    'url': 'https://example.com/test2',
    'symbol': SYMBOL,
    'sentiment': 0.88,  # Positive sentiment > 0
    'timestamp_ms': news2_ts
}
print(f"3. Emitting News 2 (Trigger) at minute 20 (sentiment=0.88)...")
producer.send('market-news', key=SYMBOL, value=news2, timestamp_ms=news2_ts)

# Watermark advancement event at minute 35
wm_time = base_time + timedelta(minutes=35)
wm_ts = int(wm_time.timestamp() * 1000)
wm_bar = {
    'symbol': SYMBOL,
    'open': 90.0, 'high': 90.0, 'low': 90.0, 'close': 90.0,
    'volume': 10.0, 'trade_count': 1.0, 'vwap': 90.0,
    'provider': 'alpaca', 'timestamp': wm_ts
}
wm_news = {
    'id': 88880099, 'author': 'WM', 'headline': 'Watermark advance',
    'source': '', 'summary': '', 'data_provider': 'alpaca', 'url': '',
    'symbol': SYMBOL, 'sentiment': 0.0, 'timestamp_ms': wm_ts
}
producer.send('stock-prices', key=SYMBOL, value=wm_bar, timestamp_ms=wm_ts)
producer.send('market-news', key=SYMBOL, value=wm_news, timestamp_ms=wm_ts)

producer.flush()
producer.close()
print("4. All test events sent! Consuming from 'trading-signals'...")

time.sleep(3)

consumer = KafkaConsumer(
    'trading-signals',
    bootstrap_servers=BROKERS,
    auto_offset_reset='earliest',
    consumer_timeout_ms=10000,
    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
)

captured = []
for msg in consumer:
    val = msg.value
    captured.append(val)
    print(f">>> CAPTURED SIGNAL: Symbol={val.get('symbol')} Signal={val.get('signal')} Time={val.get('signal_time')}")

consumer.close()

if any(s.get('signal') == 'BUY' for s in captured):
    print("\nVERIFICATION RESULT: BUY SIGNAL SUCCESSFULLY EMITTED AND CAPTURED!")
else:
    print(f"\nCaptured {len(captured)} signals total.")
