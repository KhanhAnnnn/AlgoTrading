"""
tests/e2e/traceability_audit.py — Cross-Tier Traceability & Correlation Audit
Audits message metadata across Redpanda 7 topics, Flink jobs, and Signal Handlers.
Extracts event timestamps, ingest timestamps, Kafka offsets, and correlation identifiers.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from kafka import KafkaConsumer, TopicPartition

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
ORDERS_DIR = os.path.join(DATA_DIR, 'orders')
os.makedirs(STATUS_DIR, exist_ok=True)

TOPICS = [
    'stock-prices',
    'market-news',
    'trading-signals',
    'crypto-trades',
    'crypto-bars-1m',
    'crypto-news',
    'crypto-signals'
]

def run_traceability_audit():
    audit_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topics": {},
        "signals_trace": {
            "stocks": [],
            "crypto": []
        },
        "orders_trace": []
    }

    consumer = KafkaConsumer(bootstrap_servers=['localhost:9092'], consumer_timeout_ms=1000)

    for t in TOPICS:
        tp = TopicPartition(t, 0)
        consumer.assign([tp])
        beg = consumer.beginning_offsets([tp])[tp]
        end = consumer.end_offsets([tp])[tp]
        total_msgs = end - beg

        topic_info = {
            "partition": 0,
            "beginning_offset": beg,
            "high_watermark": end,
            "total_messages": total_msgs,
            "sample_latest": None
        }

        if end > beg:
            # Read last message
            consumer.seek(tp, end - 1)
            msg = next(consumer)
            try:
                val = json.loads(msg.value.decode('utf-8'))
            except Exception:
                val = str(msg.value[:100])

            topic_info["sample_latest"] = {
                "offset": msg.offset,
                "timestamp_kafka_ms": msg.timestamp,
                "key": msg.key.decode('utf-8') if msg.key else None,
                "data": val
            }

        audit_report["topics"][t] = topic_info

    # Collect existing Stocks signals safely
    tp_sig = TopicPartition('trading-signals', 0)
    consumer.assign([tp_sig])
    beg_sig = consumer.beginning_offsets([tp_sig])[tp_sig]
    end_sig = consumer.end_offsets([tp_sig])[tp_sig]
    if end_sig > beg_sig:
        consumer.seek(tp_sig, beg_sig)
        for _ in range(end_sig - beg_sig):
            try:
                msg = next(consumer)
                sig_data = json.loads(msg.value.decode('utf-8'))
                audit_report["signals_trace"]["stocks"].append({
                    "offset": msg.offset,
                    "kafka_timestamp": msg.timestamp,
                    "signal_time": sig_data.get("signal_time"),
                    "symbol": sig_data.get("symbol"),
                    "signal": sig_data.get("signal"),
                    "correlation_id": f"SIG-STOCKS-{sig_data.get('symbol')}-{sig_data.get('signal')}-{str(sig_data.get('signal_time')).replace(' ', '_').replace(':', '')}"
                })
            except Exception:
                break

    # Collect existing Crypto signals safely
    tp_csig = TopicPartition('crypto-signals', 0)
    consumer.assign([tp_csig])
    beg_csig = consumer.beginning_offsets([tp_csig])[tp_csig]
    end_csig = consumer.end_offsets([tp_csig])[tp_csig]
    if end_csig > beg_csig:
        consumer.seek(tp_csig, beg_csig)
        for _ in range(end_csig - beg_csig):
            try:
                msg = next(consumer)
                sig_data = json.loads(msg.value.decode('utf-8'))
                audit_report["signals_trace"]["crypto"].append({
                    "offset": msg.offset,
                    "kafka_timestamp": msg.timestamp,
                    "signal_time": sig_data.get("signal_time"),
                    "symbol": sig_data.get("symbol"),
                    "signal": sig_data.get("signal"),
                    "price": sig_data.get("price"),
                    "sentiment": sig_data.get("sentiment"),
                    "correlation_id": f"SIG-CRYPTO-{sig_data.get('symbol')}-{sig_data.get('signal')}-{str(sig_data.get('signal_time')).replace(' ', '_').replace(':', '')}"
                })
            except Exception:
                break

    consumer.close()

    # Load persistent order intents
    crypto_intent_file = os.path.join(ORDERS_DIR, 'crypto_order_intent.json')
    if os.path.exists(crypto_intent_file):
        try:
            with open(crypto_intent_file, 'r', encoding='utf-8') as f:
                intents = json.load(f)
                for it in intents:
                    audit_report["orders_trace"].append({
                        "type": "CRYPTO_INTENT",
                        "client_order_id": it.get("client_order_id"),
                        "dedup_key": it.get("dedup_key"),
                        "symbol": it.get("symbol"),
                        "signal": it.get("signal"),
                        "signal_time": it.get("signal_time"),
                        "price": it.get("price"),
                        "mode": it.get("mode"),
                        "status": it.get("order_result", {}).get("status")
                    })
        except Exception as e:
            audit_report["orders_trace_error"] = str(e)

    # Load Alpaca Paper Order Receipt from GĐ10.6
    paper_receipt_file = os.path.join(ORDERS_DIR, 'gd10_6_paper_order_receipt.json')
    if os.path.exists(paper_receipt_file):
        try:
            with open(paper_receipt_file, 'r', encoding='utf-8') as f:
                receipt = json.load(f)
                audit_report["orders_trace"].append({
                    "type": "ALPACA_PAPER_EXECUTED",
                    "order_id": receipt.get("order_id"),
                    "client_order_id": receipt.get("client_order_id"),
                    "symbol": receipt.get("symbol"),
                    "side": receipt.get("side"),
                    "filled_qty": receipt.get("filled_qty"),
                    "filled_avg_price": receipt.get("filled_avg_price"),
                    "execution_timestamp": receipt.get("execution_timestamp"),
                    "endpoint": receipt.get("endpoint")
                })
        except Exception as e:
            audit_report["paper_receipt_error"] = str(e)

    output_path = os.path.join(STATUS_DIR, 'gd12_traceability_audit.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(audit_report, f, indent=2)

    print(f"Traceability audit completed successfully. Written to: {output_path}")
    print(f"Summary: {len(audit_report['topics'])} topics audited, {len(audit_report['signals_trace']['stocks'])} stocks signals traced, {len(audit_report['orders_trace'])} order traces found.")
    return audit_report

if __name__ == '__main__':
    run_traceability_audit()

