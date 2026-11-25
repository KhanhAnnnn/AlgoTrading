import json
import time
from kafka import KafkaConsumer, TopicPartition

brokers = ['localhost:9092', 'localhost:9093']

def get_latest_kafka_records():
    results = {}
    
    # 1. stock-prices
    consumer = KafkaConsumer(
        bootstrap_servers=brokers,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=1500,
        value_deserializer=lambda v: json.loads(v.decode('utf-8', errors='ignore'))
    )
    tp = TopicPartition('stock-prices', 0)
    consumer.assign([tp])
    end_offset = consumer.end_offsets([tp])[tp]
    start_offset = max(0, end_offset - 4500)
    consumer.seek(tp, start_offset)
    
    latest_nvda = None
    latest_aapl = None
    for msg in consumer:
        val = msg.value
        sym = val.get('symbol')
        if sym == 'NVDA':
            latest_nvda = val
        elif sym == 'AAPL':
            latest_aapl = val
    consumer.close()
    
    results['kafka_latest_nvda'] = latest_nvda
    results['kafka_latest_aapl'] = latest_aapl
    
    # 2. market-news
    consumer = KafkaConsumer(
        bootstrap_servers=brokers,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=1500,
        value_deserializer=lambda v: json.loads(v.decode('utf-8', errors='ignore'))
    )
    tp = TopicPartition('market-news', 0)
    consumer.assign([tp])
    end_offset = consumer.end_offsets([tp])[tp]
    start_offset = max(0, end_offset - 20)
    consumer.seek(tp, start_offset)
    latest_news = None
    for msg in consumer:
        latest_news = msg.value
    consumer.close()
    results['kafka_latest_news'] = latest_news

    # 3. trading-signals
    consumer = KafkaConsumer(
        bootstrap_servers=brokers,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=1500,
        value_deserializer=lambda v: json.loads(v.decode('utf-8', errors='ignore'))
    )
    tp = TopicPartition('trading-signals', 0)
    consumer.assign([tp])
    end_offset = consumer.end_offsets([tp])[tp]
    start_offset = max(0, end_offset - 10)
    consumer.seek(tp, start_offset)
    latest_signal = None
    for msg in consumer:
        latest_signal = msg.value
    consumer.close()
    results['kafka_latest_signal'] = latest_signal

    return results

if __name__ == '__main__':
    data = get_latest_kafka_records()
    print(json.dumps(data, indent=2))
