import sys
import os

sys.path.insert(0, 'D:/AlgoTrading')
from libs.alpaca_config.keys import config
import importlib.util
spec = importlib.util.spec_from_file_location("prices_producer", "D:/AlgoTrading/prices-producer.py")
prices_producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prices_producer)

brokers = config['redpanda_brokers']
print("Connecting to Redpanda brokers:", brokers)
producer = prices_producer.get_producer(brokers)

print("Ingesting historical bars for AAPL...")
prices_producer.produce_historical_price(
    redpanda_client=producer,
    topic='stock-prices',
    symbol='AAPL',
    days_back=5
)

producer.close()
print("AAPL ingestion finished!")
