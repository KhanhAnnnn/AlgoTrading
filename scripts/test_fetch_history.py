import os
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv('d:/AlgoTrading/.env')
key = os.environ.get('ALPACA_KEY_ID')
secret = os.environ.get('ALPACA_SECRET_KEY')

print('Key configured:', bool(key and secret))

from alpaca.data.enums import DataFeed

try:
    stock_client = StockHistoricalDataClient(key, secret)
    req = StockBarsRequest(
        symbol_or_symbols=['NVDA', 'AAPL'],
        timeframe=TimeFrame.Minute,
        start=datetime.now(timezone.utc) - timedelta(days=30),
        feed=DataFeed.IEX
    )
    stock_bars = stock_client.get_stock_bars(req)
    for sym in ['NVDA', 'AAPL']:
        bars = stock_bars[sym] if sym in stock_bars else []
        print(f"Stock {sym} 1m bars fetched: {len(bars)}")
except Exception as e:
    print("Stock fetch error:", e)

try:
    crypto_client = CryptoHistoricalDataClient(key, secret)
    creq = CryptoBarsRequest(
        symbol_or_symbols=['BTC/USD', 'ETH/USD'],
        timeframe=TimeFrame.Minute,
        start=datetime.now(timezone.utc) - timedelta(days=7),
        limit=10000
    )
    crypto_bars = crypto_client.get_crypto_bars(creq)
    for sym in ['BTC/USD', 'ETH/USD']:
        cbars = crypto_bars[sym] if sym in crypto_bars else []
        print(f"Crypto {sym} 1m bars fetched: {len(cbars)}")
except Exception as e:
    print("Crypto fetch error:", e)
