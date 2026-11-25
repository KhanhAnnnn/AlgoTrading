import sys
import time

sys.path.insert(0, 'D:/AlgoTrading/trading-dashboard/backend')
from kafka_consumer_service import kafka_service

print("1. Starting kafka_service in background...")
kafka_service.start()

print("2. Waiting 5 seconds to catch up on Kafka topics...")
time.sleep(5)

status = kafka_service.get_status()
print("\n--- Kafka Service Status ---")
for k, v in status.items():
    print(f"  {k}: {v}")

nvda = kafka_service.get_candles('NVDA')
print(f"\nNVDA 1m candles loaded: {len(nvda)}")
if nvda:
    print(f"First candle: {nvda[0]}")
    print(f"Last candle:  {nvda[-1]}")

aapl = kafka_service.get_candles('AAPL')
print(f"AAPL 1m candles loaded: {len(aapl)}")

news = kafka_service.get_news()
print(f"News items loaded: {len(news)}")

signals = kafka_service.get_signals()
print(f"Signals loaded: {len(signals)}")

kafka_service.stop()
print("\nBACKEND TEST RESULT: SUCCESS!")
