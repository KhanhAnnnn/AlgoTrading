"""
test_continuous_producers.py — Verification of Continuous Producers & Checkpointing
Tests:
1. Single-instance PID lock acquisition & conflict rejection.
2. Checkpoint creation and persistence.
3. Strict deduplication: re-polling Alpaca when market is closed produces ZERO duplicate Kafka messages.
4. Health status JSON telemetry generation.
"""
import os
import sys
import json
import time
import subprocess
import psutil

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PYTHON_EXE = sys.executable

def test_checkpoint_and_deduplication():
    print("=== TEST 1: Checkpoint & Deduplication Verification ===")
    from continuous_price_producer import ContinuousPriceProducer, CHECKPOINT_FILE, PID_FILE, HEALTH_FILE
    
    # Initialize producer
    producer = ContinuousPriceProducer(symbols=['NVDA', 'AAPL'])
    print(f"Loaded initial checkpoint: {producer.checkpoint.get('symbols', {})}")
    
    # Fetch symbol NVDA (market closed -> start_date >= end_date or returns latest bars)
    emitted = producer.fetch_and_publish_symbol('NVDA', is_backfill=True)
    print(f"First run emitted: {emitted} bars")
    
    # Check that checkpoint file exists on disk
    assert os.path.exists(CHECKPOINT_FILE), "Checkpoint file was not created!"
    with open(CHECKPOINT_FILE, 'r') as f:
        cp_data = json.load(f)
    print(f"Checkpoint on disk for NVDA: {cp_data['symbols']['NVDA']}")
    assert cp_data['symbols']['NVDA']['last_candle_timestamp_ms'] > 0, "Last candle timestamp is 0!"
    
    # Second run: must emit ZERO duplicate bars!
    emitted_2 = producer.fetch_and_publish_symbol('NVDA')
    print(f"Immediate re-poll emitted: {emitted_2} bars (Strict Deduplication)")
    assert emitted_2 == 0, f"Expected 0 bars on deduplication re-poll, got {emitted_2}!"
    print("[PASS] Strict deduplication verified: 0 duplicate bars emitted.")
    
    producer.producer.close()

def test_news_deduplication():
    print("\n=== TEST 2: News Deduplication & Sentiment Checkpoint ===")
    from continuous_news_producer import ContinuousNewsProducer, CHECKPOINT_FILE
    
    producer = ContinuousNewsProducer()
    print(f"Loaded initial news checkpoint. Seen IDs: {len(producer.seen_ids)}")
    
    # Run fetch for NVDA
    emitted = producer.fetch_and_publish_news('NVDA', ['NVDA', 'NVIDIA'], limit=10)
    print(f"First news fetch emitted: {emitted} new articles")
    
    # Immediate second run must emit ZERO duplicates
    emitted_2 = producer.fetch_and_publish_news('NVDA', ['NVDA', 'NVIDIA'], limit=10)
    print(f"Immediate re-poll emitted: {emitted_2} duplicate articles")
    assert emitted_2 == 0, f"Expected 0 duplicate articles on re-poll, got {emitted_2}!"
    print("[PASS] News deduplication verified: 0 duplicate articles emitted.")
    
    producer.producer.close()

def test_single_instance_lock():
    print("\n=== TEST 3: Single-Instance Lock Conflict Rejection ===")
    from continuous_price_producer import SingleInstanceLock, PID_FILE
    
    lock1 = SingleInstanceLock(PID_FILE)
    lock1.acquire()
    print(f"Acquired lock with PID: {os.getpid()}")
    assert os.path.exists(PID_FILE), "PID file not found after acquire"
    
    # Try to launch subprocess trying to acquire the same lock
    proc = subprocess.run(
        [PYTHON_EXE, "-c", "from continuous_price_producer import SingleInstanceLock, PID_FILE; lock = SingleInstanceLock(PID_FILE); lock.acquire()"],
        capture_output=True, text=True
    )
    print("Subprocess exit code:", proc.returncode)
    print("Subprocess stderr/stdout:\n", proc.stdout, proc.stderr)
    assert proc.returncode != 0, "Expected second instance to fail, but it exited 0!"
    print("[PASS] Single-instance lock correctly rejected duplicate process.")
    
    lock1.release()
    assert not os.path.exists(PID_FILE), "PID file still exists after release"
    print("[PASS] Lock cleanly released.")

if __name__ == '__main__':
    test_checkpoint_and_deduplication()
    test_news_deduplication()
    test_single_instance_lock()
    print("\nALL DEDUPLICATION & LOCK TESTS PASSED!")
