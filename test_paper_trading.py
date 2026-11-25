"""
test_paper_trading.py — Verified Paper Trading Execution Test
Submits a controlled 1-share paper order for NVDA to https://paper-api.alpaca.markets
and verifies its presence via Alpaca REST API.
"""
import os
import sys
import json
import requests

# Load config from libs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
from alpaca_config.keys import config

KEY_ID = config.get('key_id', '')
SECRET_KEY = config.get('secret_key', '')
BASE_URL = config.get('trade_api_base_url', 'https://paper-api.alpaca.markets')

print("=" * 60)
print("PHASE 7 — ALPACA PAPER TRADING VERIFICATION")
print("=" * 60)

# Safety check 1: Base URL must contain paper-api
if 'paper-api' not in BASE_URL:
    print(f"CRITICAL ERROR: BASE_URL '{BASE_URL}' is NOT a paper trading endpoint! ABORTING.")
    sys.exit(1)

# Safety check 2: Credentials check
if not KEY_ID or not SECRET_KEY:
    print("CRITICAL ERROR: Alpaca credentials missing from .env! ABORTING.")
    sys.exit(1)

headers = {
    'APCA-API-KEY-ID': KEY_ID,
    'APCA-API-SECRET-KEY': SECRET_KEY,
    'Content-Type': 'application/json',
}

# 1. Check account state first
print(f"1. Querying account from {BASE_URL}/v2/account ...")
resp_acc = requests.get(f"{BASE_URL}/v2/account", headers=headers, timeout=10)
if resp_acc.status_code != 200:
    print(f"ERROR: Could not fetch account info: {resp_acc.status_code} {resp_acc.text}")
    sys.exit(1)

account = resp_acc.json()
print(f"Account ID:       {account.get('id')}")
print(f"Status:           {account.get('status')}")
print(f"Currency:         {account.get('currency')}")
print(f"Cash:             ${account.get('cash')}")
print(f"Buying Power:     ${account.get('buying_power')}")
print(f"Pattern Daytrader:{account.get('pattern_day_trader')}")

# 2. Submit test order (1 share of NVDA, side: buy, type: market, time_in_force: gtc)
symbol = 'NVDA'
qty = 1
side = 'buy'

order_payload = {
    'symbol': symbol,
    'qty': str(qty),
    'side': side,
    'type': 'market',
    'time_in_force': 'gtc'
}

print(f"\n2. Submitting Paper Market Order: {qty} share(s) of {symbol} (side={side}) ...")
resp_order = requests.post(f"{BASE_URL}/v2/orders", headers=headers, json=order_payload, timeout=15)

if resp_order.status_code not in (200, 201):
    print(f"ERROR: Order submission failed: {resp_order.status_code} {resp_order.text}")
    sys.exit(1)

order_data = resp_order.json()
order_id = order_data.get('id')
client_order_id = order_data.get('client_order_id')
order_status = order_data.get('status')
created_at = order_data.get('created_at')

print("\n--- ORDER SUBMITTED SUCCESSFULLY ---")
print(f"Order ID:         {order_id}")
print(f"Client Order ID:  {client_order_id}")
print(f"Symbol:           {order_data.get('symbol')}")
print(f"Quantity:         {order_data.get('qty')}")
print(f"Side:             {order_data.get('side')}")
print(f"Type:             {order_data.get('type')}")
print(f"Time in Force:    {order_data.get('time_in_force')}")
print(f"Status:           {order_status}")
print(f"Submitted At:     {created_at}")

# 3. Verify order in orders list
print(f"\n3. Querying order details for ID {order_id} to verify persistence ...")
resp_check = requests.get(f"{BASE_URL}/v2/orders/{order_id}", headers=headers, timeout=10)
if resp_check.status_code == 200:
    verified_order = resp_check.json()
    print(f"Verification query returned status 200 OK.")
    print(f"Verified Order ID:     {verified_order.get('id')}")
    print(f"Verified Order Status: {verified_order.get('status')}")
    print(f"Asset Class:           {verified_order.get('asset_class')}")
    print("\n============================================================")
    print("PHASE 7 ACCEPTANCE RESULT: PAPER TRADING TEST ORDER PASSED!")
    print("============================================================")
else:
    print(f"Warning: Could not fetch order {order_id}: {resp_check.status_code}")
