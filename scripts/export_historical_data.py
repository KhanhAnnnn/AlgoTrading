import os
import json
import pandas as pd
from kafka import KafkaConsumer, TopicPartition

os.makedirs('data/historical', exist_ok=True)
consumer = KafkaConsumer(bootstrap_servers=['localhost:9092'], consumer_timeout_ms=1000)

for topic in ['stock-prices', 'market-news', 'crypto-bars-1m', 'crypto-news']:
    tp = TopicPartition(topic, 0)
    consumer.assign([tp])
    beg = consumer.beginning_offsets([tp])[tp]
    end = consumer.end_offsets([tp])[tp]
    
    rows = []
    if end > beg:
        consumer.seek(tp, beg)
        for _ in range(end - beg):
            try:
                msg = next(consumer)
                rows.append(json.loads(msg.value.decode('utf-8')))
            except Exception:
                break
    df = pd.DataFrame(rows)
    topic_clean = topic.replace('-', '_')
    out_csv = f'data/historical/{topic_clean}.csv'
    df.to_csv(out_csv, index=False)
    print(f'Exported {topic}: {len(df)} rows -> {out_csv}')

consumer.close()

