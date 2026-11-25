import json
from kafka import KafkaConsumer

brokers = ['localhost:9092', 'localhost:9093']

for topic in ['stock-prices', 'market-news', 'trading-signals']:
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=brokers,
        auto_offset_reset='earliest',
        consumer_timeout_ms=3000,
        value_deserializer=lambda v: json.loads(v.decode('utf-8', errors='ignore'))
    )
    count = 0
    sample = None
    for msg in consumer:
        count += 1
        if sample is None:
            sample = msg.value
    consumer.close()
    print(f"\n=== TOPIC: {topic} ===")
    print(f"Total messages available: {count}")
    if sample:
        print(f"Sample keys: {list(sample.keys())}")
        print(f"Sample value: {sample}")
