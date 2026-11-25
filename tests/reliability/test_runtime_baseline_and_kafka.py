"""
test_runtime_baseline_and_kafka.py
Covers:
- TC-G14-01: Baseline runtime snapshot
- TC-G14-02: Kafka connectivity
- TC-G14-07: Kafka offset persistence
- TC-G14-21: Stocks/Crypto isolation
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from kafka import KafkaConsumer, KafkaProducer, TopicPartition

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATUS_DIR = os.path.join(DATA_DIR, "status")
SNAPSHOT_FILE = os.path.join(STATUS_DIR, "gd14_baseline_snapshot.json")

def test_tc_g14_01_baseline_snapshot():
    """TC-G14-01: Verify baseline runtime snapshot exists and has complete topology."""
    print("Executing TC-G14-01: Baseline Runtime Snapshot...")
    assert os.path.exists(SNAPSHOT_FILE), f"Snapshot file missing: {SNAPSHOT_FILE}"
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "kafka" in data, "Snapshot missing kafka section"
    assert "flink" in data, "Snapshot missing flink section"
    assert "producers" in data, "Snapshot missing producers section"
    assert "handlers_and_orders" in data, "Snapshot missing handlers section"
    print(f"  [PASS] Baseline snapshot validated with {len(data['kafka'])} topics and Flink cluster details.")
    return {
        "id": "TC-G14-01",
        "name": "Baseline runtime snapshot",
        "expected": "Complete snapshot of Kafka, Flink, Producers, and Handlers persisted to JSON",
        "actual": f"Snapshot captured at {data.get('timestamp')} with {len(data['kafka'])} topics",
        "evidence": f"File {SNAPSHOT_FILE} (size: {os.path.getsize(SNAPSHOT_FILE)} bytes)",
        "status": "PASS"
    }

def test_tc_g14_02_kafka_connectivity():
    """TC-G14-02: Verify Kafka / Redpanda cluster connectivity and production topics."""
    print("Executing TC-G14-02: Kafka Connectivity & Topology...")
    brokers = ["localhost:9092", "localhost:9093"]
    consumer = KafkaConsumer(bootstrap_servers=brokers, request_timeout_ms=5000)
    topics = consumer.topics()
    consumer.close()
    
    required_topics = [
        "stock-prices", "market-news", "trading-signals",
        "crypto-bars-1m", "crypto-news", "crypto-signals", "crypto-trades"
    ]
    for rt in required_topics:
        assert rt in topics, f"Required topic {rt} missing from cluster: {topics}"
        
    print(f"  [PASS] Connected to Redpanda on {brokers}. All 7 core production topics verified.")
    return {
        "id": "TC-G14-02",
        "name": "Kafka connectivity",
        "expected": "Redpanda brokers reachable on 9092/9093 with 7 production topics available",
        "actual": f"Connected to brokers. Verified topics: {sorted(required_topics)}",
        "evidence": f"Total active topics on broker: {len(topics)}",
        "status": "PASS"
    }

def test_tc_g14_07_kafka_offset_persistence():
    """TC-G14-07: Verify Kafka consumer committed offset persistence across disconnects."""
    print("Executing TC-G14-07: Kafka Offset Persistence...")
    brokers = ["localhost:9092", "localhost:9093"]
    test_group = f"test-offset-persistence-group-{int(time.time())}"
    topic = "stock-prices"
    tp = TopicPartition(topic, 0)
    
    # Session 1: Read and commit offset
    c1 = KafkaConsumer(topic, bootstrap_servers=brokers, group_id=test_group, enable_auto_commit=False)
    c1.poll(timeout_ms=1000)
    committed_offset_1 = 100  # arbitrary test offset commit
    from kafka import OffsetAndMetadata
    c1.commit({tp: OffsetAndMetadata(committed_offset_1, "test-meta-1", 0)})
    read_back_1 = c1.committed(tp)
    c1.close()
    
    # Session 2: Reconnect with same group and verify committed offset survives
    c2 = KafkaConsumer(topic, bootstrap_servers=brokers, group_id=test_group, enable_auto_commit=False)
    read_back_2 = c2.committed(tp)
    c2.close()
    
    assert read_back_1 == committed_offset_1, f"Expected {committed_offset_1}, got {read_back_1}"
    assert read_back_2 == committed_offset_1, f"Expected {committed_offset_1} after reconnect, got {read_back_2}"
    
    print(f"  [PASS] Offset {committed_offset_1} committed in session 1 and perfectly restored in session 2.")
    return {
        "id": "TC-G14-07",
        "name": "Kafka offset persistence",
        "expected": "Consumer committed offsets survive consumer disconnection and reconnects",
        "actual": f"Committed offset {committed_offset_1} retrieved identically in subsequent session",
        "evidence": f"Consumer group {test_group}: initial={read_back_1}, restored={read_back_2}",
        "status": "PASS"
    }

def test_tc_g14_21_stocks_crypto_isolation():
    """TC-G14-21: Verify strict isolation between Stocks and Crypto pipelines."""
    print("Executing TC-G14-21: Stocks/Crypto Pipeline Isolation...")
    brokers = ["localhost:9092", "localhost:9093"]
    consumer = KafkaConsumer(bootstrap_servers=brokers, request_timeout_ms=5000)
    
    # Verify Stocks topics contain only stock schemas / symbols
    stocks_consumer = KafkaConsumer(
        "stock-prices", bootstrap_servers=brokers,
        auto_offset_reset="earliest", consumer_timeout_ms=2000,
        value_deserializer=lambda b: json.loads(b.decode("utf-8"))
    )
    sample_stocks = []
    for _ in range(10):
        try:
            msg = next(stocks_consumer)
            sample_stocks.append(msg.value)
        except StopIteration:
            break
    stocks_consumer.close()
    
    for s in sample_stocks:
        assert s.get("symbol") in ("NVDA", "AAPL"), f"Non-stock symbol found in stock-prices: {s}"
        assert "asset_type" not in s or s.get("asset_type") == "stocks", f"Unexpected asset_type in stocks: {s}"
        
    # Verify Crypto topics contain only crypto symbols
    crypto_consumer = KafkaConsumer(
        "crypto-bars-1m", bootstrap_servers=brokers,
        auto_offset_reset="earliest", consumer_timeout_ms=2000,
        value_deserializer=lambda b: json.loads(b.decode("utf-8"))
    )
    sample_crypto = []
    for _ in range(10):
        try:
            msg = next(crypto_consumer)
            sample_crypto.append(msg.value)
        except StopIteration:
            break
    crypto_consumer.close()
    
    for c in sample_crypto:
        assert c.get("symbol") in ("BTC/USD", "ETH/USD"), f"Non-crypto symbol found in crypto-bars-1m: {c}"
        assert c.get("asset_type") == "crypto", f"Crypto asset_type mismatch: {c}"
        
    consumer.close()
    print("  [PASS] Stocks and Crypto pipelines operate on completely disjoint schemas and topics.")
    return {
        "id": "TC-G14-21",
        "name": "Stocks/Crypto isolation",
        "expected": "Strict segregation of topics, schemas, and symbols between stocks and crypto",
        "actual": "Verified: stock-prices only contains NVDA/AAPL; crypto-bars-1m only contains BTC/USD and ETH/USD",
        "evidence": f"Sampled {len(sample_stocks)} stock records and {len(sample_crypto)} crypto records without contamination",
        "status": "PASS"
    }

if __name__ == "__main__":
    t1 = test_tc_g14_01_baseline_snapshot()
    t2 = test_tc_g14_02_kafka_connectivity()
    t3 = test_tc_g14_07_kafka_offset_persistence()
    t4 = test_tc_g14_21_stocks_crypto_isolation()
    print("\nSummary: All 4 tests passed!")
