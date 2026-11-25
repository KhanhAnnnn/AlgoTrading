from kafka import KafkaConsumer, TopicPartition
import json
from datetime import datetime, timezone

brokers = ['localhost:9092', 'localhost:9093']
topics = ['stock-prices', 'market-news', 'trading-signals']

for topic in topics:
    consumer = KafkaConsumer(
        bootstrap_servers=brokers,
        auto_offset_reset='earliest',
        enable_auto_commit=False,
        consumer_timeout_ms=3000
    )
    partitions = consumer.partitions_for_topic(topic)
    print(f"=== Topic: {topic} (partitions: {partitions}) ===")
    if partitions:
        tps = [TopicPartition(topic, p) for p in partitions]
        beginning = consumer.beginning_offsets(tps)
        end = consumer.end_offsets(tps)
        for tp in tps:
            print(f"  Partition {tp.partition}: start_offset={beginning[tp]}, end_offset={end[tp]}, total_records={end[tp] - beginning[tp]}")
        
        # Read latest record to check timestamp
        for tp in tps:
            if end[tp] > 0:
                consumer.assign([tp])
                consumer.seek(tp, max(0, end[tp] - 1))
                for msg in consumer:
                    val = json.loads(msg.value.decode('utf-8'))
                    key_str = msg.key.decode('utf-8') if msg.key else 'None'
                    ts = msg.timestamp
                    ts_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat() if ts else 'N/A'
                    print(f"  Latest record in P{tp.partition}: key={key_str}, msg_timestamp={ts} ({ts_dt})")
                    sample = {k: val[k] for k in list(val.keys())[:6]}
                    print(f"    sample data: {sample}")
                    if 'timestamp' in val:
                        t_val = val['timestamp']
                        t_dt = datetime.fromtimestamp(t_val / 1000 if t_val > 1e11 else t_val, tz=timezone.utc).isoformat()
                        print(f"    timestamp in val: {t_val} -> {t_dt}")
                    if 'timestamp_ms' in val:
                        t_ms = val['timestamp_ms']
                        t_dt = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat()
                        print(f"    timestamp_ms in val: {t_ms} -> {t_dt}")
                    break
    consumer.close()
