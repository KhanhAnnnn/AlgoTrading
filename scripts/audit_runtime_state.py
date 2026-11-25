"""
audit_runtime_state.py — GĐ14 Baseline Runtime & State Audit
Captures full baseline snapshot across Redpanda, Kafka topics, offsets, Flink, producers, handlers, and persistence files.
"""
import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from datetime import datetime, timezone
import requests
from kafka import KafkaConsumer, TopicPartition

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATUS_DIR = os.path.join(DATA_DIR, "status")
CHECKPOINTS_DIR = os.path.join(DATA_DIR, "checkpoints")
ORDERS_DIR = os.path.join(DATA_DIR, "orders")

def audit_kafka():
    print("[1/5] Auditing Kafka / Redpanda Cluster...")
    brokers = ["localhost:9092", "localhost:9093"]
    consumer = KafkaConsumer(bootstrap_servers=brokers, request_timeout_ms=5000)
    topics = sorted(list(consumer.topics()))
    topic_data = {}
    for t in topics:
        partitions = consumer.partitions_for_topic(t)
        p_data = {}
        if partitions:
            for p in sorted(list(partitions)):
                tp = TopicPartition(t, p)
                beg = consumer.beginning_offsets([tp])
                end = consumer.end_offsets([tp])
                p_data[str(p)] = {
                    "beginning_offset": beg[tp],
                    "end_offset": end[tp],
                    "message_count": end[tp] - beg[tp]
                }
        topic_data[t] = p_data
    consumer.close()
    return topic_data

def audit_flink():
    print("[2/5] Auditing Flink JobManager & State...")
    base_url = "http://localhost:8081"
    res = {}
    try:
        overview = requests.get(f"{base_url}/overview", timeout=5).json()
        jobs = requests.get(f"{base_url}/jobs/overview", timeout=5).json()
        res["overview"] = overview
        res["jobs"] = jobs.get("jobs", [])
        
        # Check config for checkpointing
        conf = requests.get(f"{base_url}/jobmanager/config", timeout=5).json()
        checkpoint_conf = {item["key"]: item["value"] for item in conf if any(k in item["key"] for k in ["check", "state", "save"])}
        res["checkpoint_config"] = checkpoint_conf
    except Exception as e:
        res["error"] = str(e)
    return res

def audit_producers():
    print("[3/5] Auditing Producer Health and Checkpoints...")
    health_files = {
        "price_producer": os.path.join(STATUS_DIR, "price_producer_health.json"),
        "news_producer": os.path.join(STATUS_DIR, "news_producer_health.json"),
        "crypto_producer": os.path.join(STATUS_DIR, "crypto_producer_health.json"),
    }
    status = {}
    for name, path in health_files.items():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    status[name] = json.load(f)
            except Exception as e:
                status[name] = {"error": str(e)}
        else:
            status[name] = "NOT_FOUND"
            
    # Checkpoints
    checkpoints = {}
    if os.path.exists(CHECKPOINTS_DIR):
        for f in os.listdir(CHECKPOINTS_DIR):
            fpath = os.path.join(CHECKPOINTS_DIR, f)
            try:
                with open(fpath, "r", encoding="utf-8") as cp_file:
                    checkpoints[f] = json.load(cp_file)
            except Exception as e:
                checkpoints[f] = {"error": str(e)}
    return {"health": status, "checkpoints": checkpoints}

def audit_handlers_and_orders():
    print("[4/5] Auditing Handlers, Orders, and Slack States...")
    state = {}
    
    # Order intents
    orders = {}
    if os.path.exists(ORDERS_DIR):
        for f in os.listdir(ORDERS_DIR):
            fpath = os.path.join(ORDERS_DIR, f)
            try:
                with open(fpath, "r", encoding="utf-8") as of:
                    orders[f] = json.load(of)
            except Exception as e:
                orders[f] = {"error": str(e)}
    state["orders"] = orders
    
    # Slack state / status files
    slack_status_files = [
        "gd11_test_ping_receipt.json",
        "gd11_slack_audit.json",
        "crypto_slack_delivery.json"
    ]
    slack_states = {}
    for sf in slack_status_files:
        p = os.path.join(STATUS_DIR, sf)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    slack_states[sf] = json.load(f)
            except Exception as e:
                slack_states[sf] = {"error": str(e)}
    state["slack"] = slack_states
    return state

def audit_dashboard_and_backend():
    print("[5/5] Auditing Backend API & Dashboard Ports...")
    backend_status = {}
    try:
        r = requests.get("http://localhost:8000/api/health", timeout=3)
        backend_status["api_health"] = r.json()
    except Exception as e:
        backend_status["api_health_error"] = str(e)
    return backend_status

def main():
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"=== GĐ14 BASELINE RUNTIME & STATE AUDIT at {timestamp} ===")
    
    snapshot = {
        "audit_version": "GD14_BASELINE_SNAPSHOT",
        "timestamp": timestamp,
        "kafka": audit_kafka(),
        "flink": audit_flink(),
        "producers": audit_producers(),
        "handlers_and_orders": audit_handlers_and_orders(),
        "backend": audit_dashboard_and_backend()
    }
    
    out_file = os.path.join(STATUS_DIR, "gd14_baseline_snapshot.json")
    os.makedirs(STATUS_DIR, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
        
    print(f"\n[OK] Baseline snapshot successfully saved to: {out_file}")

if __name__ == "__main__":
    main()
